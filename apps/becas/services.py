"""
Becas — fase 1: seguimiento de beneficiarios.

SIBU **no adjudica ni desembolsa** becas: eso lo hace el sistema institucional.
Aquí se registra quién es beneficiario, se verifica que siga matriculado y se
deja constancia del seguimiento. El ciclo convocatoria→adjudicación llega en
fase 2 vía `id_externo`.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.academico.providers import CargaArchivoProvider
from apps.auditoria.models import LogAuditoria
from apps.core.models import PeriodoAcademico

from .models import BecaBeneficiario, SeguimientoBeca

logger = logging.getLogger(__name__)


def _provider():
    """
    Reutiliza el proveedor académico del Sprint 1.

    La matrícula es dato institucional: si mañana se consulta al SGA por API en
    vez de leer la réplica de la ficha, aquí no cambia nada.
    """
    return CargaArchivoProvider()


@transaction.atomic
def registrar_beneficiario(
    *,
    expediente,
    tipo_beca,
    periodo_desde: PeriodoAcademico,
    profesional,
    periodo_hasta=None,
    monto_o_porcentaje: str = "",
    resolucion: str = "",
    origen: str = BecaBeneficiario.Origen.MANUAL,
    id_externo: str = "",
    usuario=None,
) -> BecaBeneficiario:
    """Registra a un beneficiario. No adjudica: deja constancia de lo adjudicado."""
    if periodo_hasta and periodo_hasta.fecha_inicio < periodo_desde.fecha_inicio:
        raise ValidationError("El periodo final no puede ser anterior al inicial.")

    # Una misma beca activa no puede duplicarse: el duplicado se leería como
    # dos adjudicaciones y falsearía cualquier conteo posterior.
    duplicada = BecaBeneficiario.objects.filter(
        expediente=expediente,
        tipo_beca=tipo_beca,
        estado__in=[BecaBeneficiario.Estado.REGISTRADO, BecaBeneficiario.Estado.EN_SEGUIMIENTO],
        eliminado_en__isnull=True,
    ).exists()
    if duplicada:
        raise ValidationError(
            f"Esta persona ya tiene una beca activa de tipo {tipo_beca}. "
            "Termine o suspenda la anterior antes de registrar otra."
        )

    beneficiario = BecaBeneficiario.objects.create(
        expediente=expediente,
        tipo_beca=tipo_beca,
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        monto_o_porcentaje=monto_o_porcentaje,
        resolucion=resolucion,
        origen=origen,
        id_externo=id_externo,
        creado_por=usuario,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        accion=LogAuditoria.Accion.CREATE,
        modulo="becas",
        entidad="BecaBeneficiario",
        entidad_id=str(beneficiario.pk),
        expediente_id=expediente.pk,
        detalle={"tipo_beca": str(tipo_beca), "resolucion": resolucion},
    )
    return beneficiario


def verificar_matricula(beneficiario: BecaBeneficiario, periodo: PeriodoAcademico, profesional):
    """
    Comprueba contra el dato institucional si el becario sigue matriculado.

    Devuelve el SeguimientoBeca creado. **No suspende automáticamente**: una
    beca es el sustento de alguien y quitarla es una decisión de Trabajo Social,
    no el efecto secundario de una consulta. El sistema informa; la persona
    decide.
    """
    cedula = beneficiario.expediente.persona.cedula
    datos = _provider().consultar_persona(cedula)

    # `consultar_persona` devuelve None solo si la PERSONA no existe. Si existe
    # pero no tiene datos académicos cargados, devuelve un dict con los campos
    # vacíos. Tratar ese vacío como "no matriculado" haría que se marcara sin
    # matrícula a un becario porque nadie subió el archivo del periodo, y de ahí
    # a suspenderle la beca hay un paso. Vacío significa "no se sabe".
    estado = (datos or {}).get("estado", "")
    estado = (estado or "").strip().lower()

    if not estado:
        vigente = None
        detalle = (
            "No hay datos académicos cargados para esta persona en el sistema. "
            "No es prueba de que no esté matriculada: puede faltar la carga del periodo."
        )
    else:
        vigente = estado in ("matriculado", "activo", "vigente")
        detalle = (
            f"Periodo consultado: {datos.get('periodo') or '—'}. "
            f"Estado institucional: {datos.get('estado') or '—'}. "
            f"Carrera: {datos.get('carrera') or '—'}."
        )

    return SeguimientoBeca.objects.create(
        beneficiario=beneficiario,
        periodo=periodo,
        tipo=SeguimientoBeca.Tipo.VERIFICACION,
        detalle=detalle,
        matricula_vigente=vigente,
        registrado_por=profesional,
    )


def registrar_seguimiento(
    beneficiario: BecaBeneficiario,
    *,
    periodo: PeriodoAcademico,
    tipo: str,
    detalle: str,
    profesional,
) -> SeguimientoBeca:
    """Entrevista, novedad o informe social."""
    if not detalle.strip():
        raise ValidationError("El seguimiento necesita un detalle.")
    seguimiento = SeguimientoBeca.objects.create(
        beneficiario=beneficiario,
        periodo=periodo,
        tipo=tipo,
        detalle=detalle,
        registrado_por=profesional,
    )
    if beneficiario.estado == BecaBeneficiario.Estado.REGISTRADO:
        beneficiario.estado = BecaBeneficiario.Estado.EN_SEGUIMIENTO
        beneficiario.save(update_fields=["estado", "actualizado_en"])
    return seguimiento


@transaction.atomic
def cambiar_estado(
    beneficiario: BecaBeneficiario, nuevo_estado: str, *, causal: str, usuario=None
) -> BecaBeneficiario:
    """
    Suspende o termina una beca.

    La causal es obligatoria: quitarle la beca a alguien sin dejar escrito por
    qué es indefendible ante un reclamo, y el reclamo llega.
    """
    if nuevo_estado not in (
        BecaBeneficiario.Estado.SUSPENDIDO,
        BecaBeneficiario.Estado.TERMINADO,
        BecaBeneficiario.Estado.EN_SEGUIMIENTO,
    ):
        raise ValidationError("Estado no admitido.")
    if (
        nuevo_estado
        in (
            BecaBeneficiario.Estado.SUSPENDIDO,
            BecaBeneficiario.Estado.TERMINADO,
        )
        and not causal.strip()
    ):
        raise ValidationError("Debe indicar la causal para suspender o terminar una beca.")
    if beneficiario.estado == BecaBeneficiario.Estado.TERMINADO:
        raise ValidationError("Una beca terminada no admite cambios de estado.")

    anterior = beneficiario.estado
    beneficiario.estado = nuevo_estado
    beneficiario.causal = causal
    beneficiario.save(update_fields=["estado", "causal", "actualizado_en"])

    LogAuditoria.objects.create(
        usuario=usuario,
        accion=LogAuditoria.Accion.UPDATE,
        modulo="becas",
        entidad="BecaBeneficiario",
        entidad_id=str(beneficiario.pk),
        expediente_id=beneficiario.expediente_id,
        detalle={"estado_anterior": anterior, "estado_nuevo": nuevo_estado, "causal": causal},
    )
    return beneficiario


def guardar_datos_bancarios(beneficiario, datos: dict) -> None:
    """
    [FASE 1: BLOQUEADO] SIBU no almacena datos bancarios.

    El campo `datos_bancarios_cifrados` existe en el modelo, pero SIBU no
    desembolsa becas: lo hace el sistema institucional. Guardar cuentas
    bancarias aquí sería asumir la responsabilidad de custodiarlas sin obtener
    nada a cambio, y el nombre del campo exige un cifrado que este proyecto
    todavía no tiene (no hay dependencia de `cryptography` ni gestión de
    claves).

    Escribir texto plano en un campo llamado "cifrados" es peor que no tener el
    campo: cualquiera que lea el esquema asumirá una protección inexistente.

    Para habilitarlo hace falta una decisión del cliente y un sprint propio:
    dependencia de cifrado, custodia y rotación de la clave, y una razón para
    que el dato viva aquí.
    """
    raise ValidationError(
        "SIBU no almacena datos bancarios en la fase 1. El desembolso lo gestiona "
        "el sistema institucional de becas."
    )


def beneficiarios_vigentes(periodo: PeriodoAcademico):
    """Becas activas que cubren el periodo indicado."""
    from django.db.models import Q

    return (
        BecaBeneficiario.objects.filter(
            estado__in=[
                BecaBeneficiario.Estado.REGISTRADO,
                BecaBeneficiario.Estado.EN_SEGUIMIENTO,
            ],
            eliminado_en__isnull=True,
            periodo_desde__fecha_inicio__lte=periodo.fecha_inicio,
        )
        .filter(Q(periodo_hasta__isnull=True) | Q(periodo_hasta__fecha_fin__gte=periodo.fecha_fin))
        .select_related("expediente__persona", "tipo_beca", "periodo_desde")
        .order_by("expediente__persona__apellidos")
    )


def resumen_por_tipo(periodo: PeriodoAcademico) -> list[dict]:
    """Conteo de beneficiarios vigentes por tipo de beca. Alimenta el S9."""
    from django.db.models import Count

    filas = (
        beneficiarios_vigentes(periodo)
        .values("tipo_beca__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    return [{"tipo": f["tipo_beca__nombre"], "total": f["total"]} for f in filas]


def expirar_vencidas(periodo_actual: PeriodoAcademico) -> int:
    """
    Marca como terminadas las becas cuyo periodo final ya pasó.

    Es un cierre administrativo por vencimiento del plazo, no una sanción: por
    eso no exige causal y deja la razón escrita.
    """
    vencidas = BecaBeneficiario.objects.filter(
        estado__in=[
            BecaBeneficiario.Estado.REGISTRADO,
            BecaBeneficiario.Estado.EN_SEGUIMIENTO,
        ],
        eliminado_en__isnull=True,
        periodo_hasta__isnull=False,
        periodo_hasta__fecha_fin__lt=periodo_actual.fecha_inicio,
    )
    return vencidas.update(
        estado=BecaBeneficiario.Estado.TERMINADO,
        causal="Cierre automático: el periodo de vigencia de la beca finalizó.",
        actualizado_en=timezone.now(),
    )
