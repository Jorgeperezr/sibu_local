"""
Lógica de negocio de Odontología (informe 6.3).

Reglas clave:
- Solo se registran piezas válidas en notación FDI.
- El odontograma conserva histórico: registrar un estado nuevo no borra el
  anterior, agrega un registro de evolución.
- Ejecutar un procedimiento con `estado_resultante` actualiza el odontograma
  automáticamente (ej. una obturación deja la pieza como "obturado").
- El índice CPO-D se calcula sobre el estado VIGENTE de cada pieza permanente.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Atencion, Expediente
from apps.expediente.services import construir_snapshot, verificar_profesional_del_servicio
from apps.usuarios.models import PerfilProfesional

from .models import (
    AtencionOdontologia,
    CatalogoProcedimiento,
    EstadoPieza,
    OdontogramaDetalle,
    Procedimiento,
    piezas_validas,
)

# Componentes del índice CPO-D (OMS): Cariados, Perdidos, Obturados.
CPOD_CARIADO = {EstadoPieza.CARIADO}
CPOD_PERDIDO = {EstadoPieza.PERDIDO}
CPOD_OBTURADO = {EstadoPieza.OBTURADO, EstadoPieza.CORONA}

# El CPO-D solo considera dentición permanente (cuadrantes 1-4).
CUADRANTES_PERMANENTES = {"1", "2", "3", "4"}


@transaction.atomic
def crear_atencion_odontologia(
    *, expediente: Expediente, profesional: PerfilProfesional, motivo: str = "", usuario=None
) -> AtencionOdontologia:
    """Crea Atencion + AtencionOdontologia en una transacción."""
    try:
        servicio = Servicio.objects.get(codigo="odontologia")
    except Servicio.DoesNotExist as exc:
        raise ValidationError("El servicio 'odontologia' no está configurado.") from exc

    verificar_profesional_del_servicio(profesional, servicio)

    atencion = Atencion.objects.create(
        expediente=expediente,
        servicio=servicio,
        profesional=profesional,
        fecha_hora=timezone.now(),
        motivo_consulta=motivo,
        snapshot_academico=construir_snapshot(expediente.persona),
        creado_por=usuario,
    )
    return AtencionOdontologia.objects.create(atencion=atencion)


def validar_pieza(pieza_fdi: str) -> str:
    """Normaliza y valida una pieza en notación FDI."""
    pieza = str(pieza_fdi).strip()
    if pieza not in piezas_validas():
        raise ValidationError(
            f"Pieza '{pieza_fdi}' no es válida en notación FDI. "
            f"Permanentes: 11-18, 21-28, 31-38, 41-48. Temporales: 51-55, 61-65, 71-75, 81-85."
        )
    return pieza


def registrar_estado_pieza(
    atencion: Atencion,
    pieza_fdi: str,
    estado: str,
    *,
    superficie: str = "",
    tipo: str = OdontogramaDetalle.TipoRegistro.INICIAL,
    observacion: str = "",
) -> OdontogramaDetalle:
    """
    Registra el estado de una pieza en el odontograma.

    No sobrescribe registros previos: el histórico completo se conserva y el
    estado vigente es siempre el último registrado.
    """
    if atencion.inmutable:
        raise ValidationError("No se puede modificar el odontograma de una atención firmada.")

    pieza = validar_pieza(pieza_fdi)
    if estado not in EstadoPieza.values:
        raise ValidationError(f"Estado '{estado}' no válido. Opciones: {EstadoPieza.values}")

    return OdontogramaDetalle.objects.create(
        atencion=atencion,
        pieza_fdi=pieza,
        superficie=superficie,
        estado_codigo=estado,
        tipo=tipo,
        observacion=observacion,
    )


def odontograma_vigente(expediente: Expediente) -> dict[str, OdontogramaDetalle]:
    """
    Estado actual de cada pieza del expediente, considerando TODAS sus
    atenciones de odontología (el odontograma es acumulativo por paciente,
    no por atención — informe 6.3).

    Devuelve {pieza_fdi: último registro}.
    """
    registros = (
        OdontogramaDetalle.objects.filter(atencion__expediente=expediente)
        .order_by("pieza_fdi", "registrado_en")
        .select_related("atencion")
    )
    vigente: dict[str, OdontogramaDetalle] = {}
    for registro in registros:
        vigente[registro.pieza_fdi] = registro  # el último en el orden gana
    return vigente


def calcular_indices(expediente: Expediente) -> dict:
    """
    Calcula el índice CPO-D (OMS) sobre el estado vigente de la dentición
    permanente del paciente.

    CPO-D = Cariados + Perdidos + Obturados. Es el indicador epidemiológico
    estándar de salud bucal y alimenta los reportes de la Unidad.
    """
    vigente = odontograma_vigente(expediente)
    cariados = perdidos = obturados = 0

    for pieza, registro in vigente.items():
        if pieza[0] not in CUADRANTES_PERMANENTES:
            continue  # el CPO-D no cuenta dentición temporal
        estado = registro.estado_codigo
        if estado in CPOD_CARIADO:
            cariados += 1
        elif estado in CPOD_PERDIDO:
            perdidos += 1
        elif estado in CPOD_OBTURADO:
            obturados += 1

    return {
        "cpod": cariados + perdidos + obturados,
        "cariados": cariados,
        "perdidos": perdidos,
        "obturados": obturados,
        "piezas_registradas": len(vigente),
    }


@transaction.atomic
def ejecutar_procedimiento(
    atencion: Atencion,
    catalogo_codigo: str,
    *,
    ejecutado_por: PerfilProfesional,
    pieza_fdi: str = "",
    superficie: str = "",
    observacion: str = "",
) -> Procedimiento:
    """
    Registra un procedimiento ejecutado y, si el catálogo define un
    `estado_resultante`, actualiza el odontograma automáticamente.

    Ejemplo: una obturación en la pieza 16 deja registro de evolución con
    estado 'obturado' sin que el odontólogo tenga que hacerlo por separado.
    """
    if atencion.inmutable:
        raise ValidationError("No se pueden registrar procedimientos en una atención firmada.")

    catalogo = CatalogoProcedimiento.objects.get(codigo=catalogo_codigo, activo=True)

    if catalogo.requiere_pieza and not pieza_fdi:
        raise ValidationError(f"El procedimiento '{catalogo.nombre}' requiere indicar la pieza.")
    if pieza_fdi:
        pieza_fdi = validar_pieza(pieza_fdi)

    procedimiento = Procedimiento.objects.create(
        atencion=atencion,
        catalogo=catalogo,
        pieza_fdi=pieza_fdi,
        superficie=superficie,
        ejecutado_por=ejecutado_por,
        observacion=observacion,
    )

    # Actualizar el odontograma si el procedimiento cambia el estado de la pieza
    if catalogo.estado_resultante and pieza_fdi:
        registrar_estado_pieza(
            atencion,
            pieza_fdi,
            catalogo.estado_resultante,
            superficie=superficie,
            tipo=OdontogramaDetalle.TipoRegistro.EVOLUCION,
            observacion=f"Por procedimiento: {catalogo.nombre}",
        )

    return procedimiento


def cerrar_atencion(atencion: Atencion, usuario=None) -> Atencion:
    """
    Cierra la atención odontológica. Exige odontograma levantado y guarda los
    índices calculados en la ficha (congelados al momento del cierre).
    """
    if atencion.estado != Atencion.Estado.BORRADOR:
        raise ValidationError(
            f"Solo se cierran atenciones en borrador (actual: {atencion.get_estado_display()})."
        )
    if not OdontogramaDetalle.objects.filter(atencion__expediente=atencion.expediente).exists():
        raise ValidationError("Debe levantarse el odontograma antes de cerrar la atención.")

    ficha = atencion.odontologia
    ficha.indices = calcular_indices(atencion.expediente)
    ficha.save(update_fields=["indices"])

    atencion.estado = Atencion.Estado.CERRADA
    atencion.save(update_fields=["estado", "actualizado_en"])
    return atencion
