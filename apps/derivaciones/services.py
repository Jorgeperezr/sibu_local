"""
Derivación interna y referencia/contrarreferencia externa (informe 5.2, 12.2, 12.3).

CONFIDENCIALIDAD — regla crítica:
El retorno de una derivación vive en el modelo `Derivacion`, que NO pertenece al
servicio destino. Si un psicólogo escribiera su evolución en `retorno_texto`, el
profesional que derivó podría leerla, burlando el sello de Psicología.

Por eso, cuando el destino es un servicio confidencial, el retorno se limita a
un acuse SIN contenido clínico: el que derivó sabe que su paciente fue atendido,
pero no qué se trabajó. Es el mismo principio del protocolo de riesgo.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Atencion
from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES, servicios_del_usuario

from .models import Contrarreferencia, Derivacion, ReferenciaExterna

# Acuse estándar cuando el destino es confidencial.
ACUSE_CONFIDENCIAL = (
    "Paciente atendido por el servicio. Por confidencialidad no se detalla el "
    "contenido clínico. Para coordinación de caso, contacte directamente al servicio."
)


# Una derivación en cualquiera de estos estados sigue viva: el destino aún no
# la ha cerrado, así que emitir otra al mismo servicio duplicaría el caso.
ESTADOS_ABIERTOS = (
    Derivacion.Estado.ENVIADA,
    Derivacion.Estado.ACEPTADA,
    Derivacion.Estado.AGENDADA,
)


def _es_confidencial(servicio: Servicio) -> bool:
    return servicio.codigo in SERVICIOS_CONFIDENCIALES


def destinos_con_derivacion_abierta(expediente) -> dict[int, str]:
    """
    Servicios a los que el paciente ya tiene una derivación viva, por id.

    Es lo que `derivar` rechaza. La pantalla lo consulta antes para no ofrecer
    un destino que va a fallar, y para decir por qué no lo ofrece.

    No abre rendija en el sello de Psicología: la EXISTENCIA de una derivación
    ya es visible para quien derivó —la trazabilidad la muestra—; lo que nunca
    sale del servicio es su contenido clínico, y aquí no se toca.
    """
    filas = (
        Derivacion.objects.filter(
            atencion_origen__expediente=expediente,
            estado__in=ESTADOS_ABIERTOS,
        )
        .select_related("servicio_destino")
        .values_list("servicio_destino_id", "servicio_destino__nombre")
    )
    return dict(filas)


@transaction.atomic
def derivar(
    atencion_origen: Atencion,
    servicio_destino: Servicio,
    *,
    motivo: str,
    resumen: str = "",
    prioridad: str = "normal",
    usuario=None,
) -> Derivacion:
    """
    Deriva un paciente a otro servicio de la Unidad.

    El `resumen` viaja hacia el destino (es información que el que deriva
    comparte voluntariamente), así que no hay problema de confidencialidad en
    esta dirección: el hueco está en el retorno.
    """
    if not motivo:
        raise ValidationError("El motivo de la derivación es obligatorio.")
    if atencion_origen.servicio_id == servicio_destino.pk:
        raise ValidationError(
            f"No tiene sentido derivar a {servicio_destino.nombre}: es el mismo servicio que emite."
        )
    if not servicio_destino.activo:
        raise ValidationError(f"El servicio {servicio_destino.nombre} no está activo.")

    abierta = Derivacion.objects.filter(
        atencion_origen__expediente=atencion_origen.expediente,
        servicio_destino=servicio_destino,
        estado__in=ESTADOS_ABIERTOS,
    ).exists()
    if abierta:
        raise ValidationError(
            f"El paciente ya tiene una derivación abierta a {servicio_destino.nombre}."
        )

    return Derivacion.objects.create(
        atencion_origen=atencion_origen,
        servicio_destino=servicio_destino,
        motivo=motivo,
        resumen=resumen,
        prioridad=prioridad,
        creado_por=usuario,
    )


def bandeja_entrada(servicio: Servicio):
    """Derivaciones dirigidas a un servicio, urgentes primero."""
    from django.db.models import Case, IntegerField, Value, When

    return (
        Derivacion.objects.filter(servicio_destino=servicio, estado__in=ESTADOS_ABIERTOS)
        .select_related("atencion_origen__expediente__persona", "atencion_origen__servicio")
        .annotate(
            _orden=Case(
                When(prioridad="urgente", then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("_orden", "creado_en")
    )


def aceptar(derivacion: Derivacion) -> Derivacion:
    """El servicio destino acepta la derivación."""
    if derivacion.estado != Derivacion.Estado.ENVIADA:
        raise ValidationError(
            f"Solo se aceptan derivaciones enviadas (actual: {derivacion.get_estado_display()})."
        )
    derivacion.estado = Derivacion.Estado.ACEPTADA
    derivacion.save(update_fields=["estado", "actualizado_en"])
    return derivacion


def rechazar(derivacion: Derivacion, motivo: str) -> Derivacion:
    """El servicio destino rechaza la derivación con justificación."""
    if not motivo:
        raise ValidationError("Debe indicar el motivo del rechazo.")
    if derivacion.estado not in {Derivacion.Estado.ENVIADA, Derivacion.Estado.ACEPTADA}:
        raise ValidationError("La derivación ya no admite rechazo.")
    derivacion.estado = Derivacion.Estado.RECHAZADA
    derivacion.retorno_texto = f"Rechazada: {motivo}"
    derivacion.save(update_fields=["estado", "retorno_texto", "actualizado_en"])
    return derivacion


def marcar_agendada(derivacion: Derivacion) -> Derivacion:
    """Se agendó la cita en el servicio destino."""
    if derivacion.estado != Derivacion.Estado.ACEPTADA:
        raise ValidationError("Solo se agendan derivaciones aceptadas.")
    derivacion.estado = Derivacion.Estado.AGENDADA
    derivacion.save(update_fields=["estado", "actualizado_en"])
    return derivacion


@transaction.atomic
def atender(derivacion: Derivacion, atencion_destino: Atencion) -> Derivacion:
    """Vincula la atención que resolvió la derivación."""
    if derivacion.estado not in {Derivacion.Estado.ACEPTADA, Derivacion.Estado.AGENDADA}:
        raise ValidationError(
            f"La derivación debe estar aceptada o agendada "
            f"(actual: {derivacion.get_estado_display()})."
        )
    if atencion_destino.servicio_id != derivacion.servicio_destino_id:
        raise ValidationError(
            f"La atención es de {atencion_destino.servicio.nombre}, pero la derivación "
            f"es a {derivacion.servicio_destino.nombre}."
        )
    if atencion_destino.expediente_id != derivacion.atencion_origen.expediente_id:
        raise ValidationError("La atención corresponde a otro paciente.")

    derivacion.atencion_destino = atencion_destino
    derivacion.estado = Derivacion.Estado.ATENDIDA
    derivacion.save(update_fields=["atencion_destino", "estado", "actualizado_en"])
    return derivacion


def retornar(derivacion: Derivacion, texto: str) -> Derivacion:
    """
    Cierra el ciclo devolviendo información al servicio que derivó.

    REGLA DE CONFIDENCIALIDAD: si el destino es un servicio confidencial, el
    texto clínico se descarta y se sustituye por un acuse. El `retorno_texto`
    es legible por quien derivó, así que no puede transportar contenido
    protegido — de lo contrario el sello de Psicología sería burlable
    escribiendo la evolución en este campo.
    """
    if derivacion.estado != Derivacion.Estado.ATENDIDA:
        raise ValidationError(
            f"Solo se retornan derivaciones atendidas (actual: {derivacion.get_estado_display()})."
        )

    if _es_confidencial(derivacion.servicio_destino):
        derivacion.retorno_texto = ACUSE_CONFIDENCIAL
    else:
        if not texto:
            raise ValidationError("El texto de retorno es obligatorio.")
        derivacion.retorno_texto = texto

    derivacion.estado = Derivacion.Estado.RETORNADA
    derivacion.save(update_fields=["estado", "retorno_texto", "actualizado_en"])
    return derivacion


def trazabilidad(expediente, usuario) -> list[dict]:
    """
    Recorrido del paciente entre servicios: quién derivó a quién y cómo terminó.

    El `usuario` no es decorativo: sobre un destino confidencial esta lista
    filtraba dos cosas a la vez. El `motivo` lo escribe quien deriva y suele
    decir por qué —es contenido—; y la sola existencia de la fila
    «→ Psicología» identifica a la persona como paciente de ese servicio,
    aunque el motivo estuviera en blanco. La marca `confidencial` que se
    devolvía no suprimía nada: solo pintaba un candado al lado del dato.

    Una derivación a un servicio confidencial la ven dos partes y nadie más:
    quien la emitió —escribió el motivo, y ocultárselo no protege a nadie
    mientras le impide seguir su propio caso— y el servicio que la recibe. Ni
    Dirección, ni Coordinación, ni administración, ni break-glass: es la misma
    regla que aplica `rbac.puede_ver_atencion`, sin excepciones.

    Lo abierto sigue abierto: una derivación de Medicina a Enfermería es
    gestión, y estrecharla dejaría el recorrido inútil para el resto.
    """
    mis_servicios = servicios_del_usuario(usuario)
    derivaciones = (
        Derivacion.objects.filter(atencion_origen__expediente=expediente)
        .select_related("atencion_origen__servicio", "servicio_destino")
        .order_by("creado_en")
    )
    filas = []
    for d in derivaciones:
        if _es_confidencial(d.servicio_destino) and not (
            d.servicio_destino_id in mis_servicios or d.atencion_origen.servicio_id in mis_servicios
        ):
            continue
        filas.append(
            {
                "fecha": d.creado_en,
                "desde": d.atencion_origen.servicio.nombre,
                "hacia": d.servicio_destino.nombre,
                "motivo": d.motivo,
                "estado": d.get_estado_display(),
                "prioridad": d.prioridad,
                "confidencial": _es_confidencial(d.servicio_destino),
            }
        )
    return filas


# ============================================================
# Referencia / contrarreferencia externa
# ============================================================


def referir_a_externo(
    atencion: Atencion,
    *,
    institucion: str,
    motivo: str,
    especialidad: str = "",
    resumen_clinico: str = "",
    usuario=None,
) -> ReferenciaExterna:
    """
    Refiere el paciente a una institución externa (informe 12.3).

    El resumen clínico sale de la Unidad, así que un servicio confidencial no
    puede emitir referencias con contenido: si Psicología deriva a un externo,
    lo hace por su propio canal, no por este.
    """
    if _es_confidencial(atencion.servicio):
        raise ValidationError(
            f"El servicio {atencion.servicio.nombre} no emite referencias externas por "
            f"este canal: su contenido es confidencial y el resumen saldría de la Unidad. "
            f"Registre la derivación externa en la ficha del proceso."
        )
    if not institucion or not motivo:
        raise ValidationError("La institución destino y el motivo son obligatorios.")

    return ReferenciaExterna.objects.create(
        atencion=atencion,
        institucion_destino=institucion,
        especialidad=especialidad,
        motivo=motivo,
        resumen_clinico=resumen_clinico,
        creado_por=usuario,
    )


def registrar_contrarreferencia(
    referencia: ReferenciaExterna,
    *,
    hallazgos: str = "",
    tratamiento: str = "",
    fecha_recepcion=None,
) -> Contrarreferencia:
    """Registra la respuesta de la institución externa."""
    if hasattr(referencia, "contrarreferencia"):
        raise ValidationError("Esta referencia ya tiene contrarreferencia registrada.")
    fecha = fecha_recepcion or timezone.localdate()
    # `creado_en` se almacena en UTC: hay que llevarlo a hora local antes de
    # comparar contra una fecha local. En Loja (UTC-5) las 19:00 ya son el día
    # siguiente en UTC, así que comparar .date() directo rechazaba toda
    # contrarreferencia registrada entre las 19:00 y medianoche.
    emitida_local = timezone.localtime(referencia.creado_en).date()
    if fecha < emitida_local:
        raise ValidationError(
            "La contrarreferencia no puede ser anterior a la emisión de la referencia."
        )
    return Contrarreferencia.objects.create(
        referencia=referencia,
        fecha_recepcion=fecha,
        hallazgos=hallazgos,
        tratamiento_instaurado=tratamiento,
    )
