"""
Lógica de negocio del módulo de citas.

- Cálculo de disponibilidad a partir de las agendas y bloqueos.
- Reserva con validación de conflictos y de la disponibilidad real del turno.
- Máquina de estados de la cita: solo transiciones válidas, reprogramación
  crea una cita nueva enlazada (audit trail).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.usuarios.models import PerfilProfesional

from .models import Agenda, BloqueoAgenda, Cita

# Transiciones válidas de estado (informe Anexo A)
TRANSICIONES = {
    Cita.Estado.RESERVADA: {
        Cita.Estado.CONFIRMADA,
        Cita.Estado.EN_ESPERA,
        Cita.Estado.CANCELADA,
        Cita.Estado.REPROGRAMADA,
        Cita.Estado.NO_ASISTIO,
    },
    Cita.Estado.CONFIRMADA: {
        Cita.Estado.EN_ESPERA,
        Cita.Estado.CANCELADA,
        Cita.Estado.REPROGRAMADA,
        Cita.Estado.NO_ASISTIO,
    },
    Cita.Estado.EN_ESPERA: {Cita.Estado.EN_ATENCION, Cita.Estado.NO_ASISTIO, Cita.Estado.CANCELADA},
    Cita.Estado.EN_ATENCION: {Cita.Estado.ATENDIDA},
    Cita.Estado.ATENDIDA: set(),
    Cita.Estado.NO_ASISTIO: set(),
    Cita.Estado.CANCELADA: set(),
    Cita.Estado.REPROGRAMADA: set(),
}

ESTADOS_ACTIVOS = {
    Cita.Estado.RESERVADA,
    Cita.Estado.CONFIRMADA,
    Cita.Estado.EN_ESPERA,
    Cita.Estado.EN_ATENCION,
}


def _en_bloqueo(profesional: PerfilProfesional, inicio: datetime, fin: datetime) -> bool:
    return BloqueoAgenda.objects.filter(
        profesional=profesional,
        fecha_inicio__lt=fin,
        fecha_fin__gt=inicio,
    ).exists()


def agendas_vigentes(profesional: PerfilProfesional, fecha: date, servicio: Servicio | None = None):
    """
    Las franjas que rigen para ese profesional ese día.

    Sin `servicio` devuelve las de todos los suyos: la persona es una, así que
    lo que ocupa su lunes por la mañana en Medicina también lo ocupa para
    Enfermería.
    """
    consulta = Agenda.objects.filter(
        profesional=profesional,
        dia_semana=fecha.weekday(),
        activa=True,
        vigente_desde__lte=fecha,
    ).filter(models_q_vigente_hasta(fecha))
    if servicio is not None:
        consulta = consulta.filter(servicio=servicio)
    return consulta


def turnos_disponibles(
    profesional: PerfilProfesional, servicio: Servicio, fecha: date
) -> list[datetime]:
    """
    Turnos libres del profesional para la fecha dada.

    Ocupado es **solapar**, no coincidir en el minuto de inicio. Comparar la
    igualdad exacta de `fecha_hora` bastaba mientras todas las citas duraban lo
    mismo; en cuanto el profesional cambia la duración de su consulta deja de
    bastar: una cita de 08:00 a 08:40 no impedía ofrecer las 08:20, y el
    paciente se sentaba encima del anterior.
    """
    agendas = agendas_vigentes(profesional, fecha, servicio)

    # Las citas vivas del día, con su duración real. Un margen de un día a cada
    # lado por si alguna cruza la medianoche, igual que en `_hay_solapamiento`.
    citas = Cita.objects.filter(
        profesional=profesional,
        fecha_hora__date__range=(fecha - timedelta(days=1), fecha + timedelta(days=1)),
        estado__in=ESTADOS_ACTIVOS,
    )
    ocupados = [(c.fecha_hora, c.fin) for c in citas]

    libres = []
    for agenda in agendas:
        for turno in agenda.generar_turnos(fecha):
            fin = turno + timedelta(minutes=agenda.duracion_turno_min)
            if any(inicio_c < fin and turno < fin_c for inicio_c, fin_c in ocupados):
                continue
            if _en_bloqueo(profesional, turno, fin):
                continue
            libres.append(turno)
    return sorted(libres)


def models_q_vigente_hasta(fecha):
    """Q helper: vigente_hasta nulo o >= fecha."""
    from django.db.models import Q

    return Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha)


@transaction.atomic
def reservar_cita(
    *,
    expediente: Expediente,
    servicio: Servicio,
    profesional: PerfilProfesional,
    fecha_hora: datetime,
    duracion_min: int | None = None,
    motivo: str = "",
    origen: str = Cita.Origen.VENTANILLA,
    usuario=None,
    cita_origen: Cita | None = None,
) -> Cita:
    """
    Reserva una cita validando: horario en agenda, sin conflicto activo,
    sin superposición con bloqueos. Levanta ValidationError si algo falla.

    **La duración la pone la agenda**, salvo que se indique otra expresamente
    (reprogramar conserva la de la cita original). Antes era un 20 fijo por
    omisión que nadie sobrescribía desde la pantalla: un profesional que
    configuraba consultas de 40 minutos veía turnos cada 40 —la pantalla sí lo
    respetaba— y la cita se grababa de 20. El sistema daba por libre la segunda
    mitad de cada consulta y admitía un segundo paciente encima del primero.
    """
    if fecha_hora < timezone.now() - timedelta(minutes=1):
        raise ValidationError("No se puede reservar en el pasado.")

    # La agenda se define en hora local (el profesional atiende de 08:00 a 16:00
    # en Loja, no en UTC). Si `fecha_hora` llega en UTC, .weekday()/.date()/.time()
    # darían el día y la hora equivocados: una cita a las 20:00 en Loja es la
    # 01:00 UTC del día SIGUIENTE. Normalizar a hora local antes de comparar.
    local_inicio = timezone.localtime(fecha_hora)

    # 1) El turno empieza dentro de alguna franja vigente ese día. Se busca por
    #    la hora de INICIO y no por el intervalo entero: hasta saber en qué
    #    franja cae no se sabe cuánto dura la consulta, y hasta saber cuánto
    #    dura no se sabe dónde termina.
    agendas = agendas_vigentes(profesional, local_inicio.date(), servicio).filter(
        hora_inicio__lte=local_inicio.time(),
        hora_fin__gt=local_inicio.time(),
    )
    agenda = agendas.first()
    if agenda is None:
        raise ValidationError("El horario está fuera de la agenda del profesional.")

    if duracion_min is None:
        duracion_min = agenda.duracion_turno_min
    fin = fecha_hora + timedelta(minutes=duracion_min)
    local_fin = timezone.localtime(fin)

    # 2) Y termina antes de que acabe la franja. Una consulta que se sale del
    #    horario no es un turno: es trabajo fuera de hora que nadie aceptó.
    if local_fin.date() != local_inicio.date() or local_fin.time() > agenda.hora_fin:
        raise ValidationError(
            f"La consulta de {duracion_min} min no cabe antes de las "
            f"{agenda.hora_fin:%H:%M}, que es cuando termina el horario."
        )

    # 3) Sin conflicto. La restricción única de BD respalda el choque exacto de
    #    `fecha_hora`, pero solo ese: una cita de 10:00 a 10:40 y otra de 10:20
    #    no coinciden en la hora de inicio y entraban las dos, dejando al
    #    profesional con dos pacientes a la vez. Hay que comparar intervalos.
    if _hay_solapamiento(profesional, fecha_hora, fin):
        raise ValidationError("El turno ya está ocupado.")

    # 4) Sin bloqueo activo
    if _en_bloqueo(profesional, fecha_hora, fin):
        raise ValidationError("El profesional tiene un bloqueo en ese horario.")

    return Cita.objects.create(
        expediente=expediente,
        servicio=servicio,
        profesional=profesional,
        fecha_hora=fecha_hora,
        duracion_min=duracion_min,
        motivo=motivo,
        origen=origen,
        cita_origen=cita_origen,
        creado_por=usuario,
    )


def _hay_solapamiento(profesional, inicio, fin, excluir_pk=None) -> bool:
    """
    ¿Choca [inicio, fin) con alguna cita activa del profesional?

    Dos intervalos se solapan si cada uno empieza antes de que el otro termine.
    El extremo derecho queda abierto a propósito: una cita puede empezar justo
    cuando termina la anterior.

    El filtro por día acota la exploración a las citas que pueden chocar; sin
    él habría que traer la agenda entera del profesional. Se toma un margen de
    un día a cada lado para no perder una cita que cruce la medianoche.
    """
    candidatas = Cita.objects.filter(
        profesional=profesional,
        estado__in=ESTADOS_ACTIVOS,
        fecha_hora__gte=inicio - timedelta(days=1),
        fecha_hora__lt=fin + timedelta(days=1),
    )
    if excluir_pk is not None:
        candidatas = candidatas.exclude(pk=excluir_pk)
    return any(cita.fecha_hora < fin and inicio < cita.fin for cita in candidatas)


def cambiar_estado(cita: Cita, nuevo: str, usuario=None) -> Cita:
    """
    Aplica una transición de estado si es válida. Registra timestamps
    (llegada_en, atendida_en) cuando corresponde.
    """
    if nuevo == cita.estado:
        return cita
    permitidos = TRANSICIONES.get(cita.estado, set())
    if nuevo not in permitidos:
        raise ValidationError(
            f"Transición inválida: {cita.estado} → {nuevo}. Permitidas: {sorted(permitidos)}"
        )
    cita.estado = nuevo
    if nuevo == Cita.Estado.EN_ESPERA and cita.llegada_en is None:
        cita.llegada_en = timezone.now()
    if nuevo == Cita.Estado.ATENDIDA:
        cita.atendida_en = timezone.now()
    cita.save(update_fields=["estado", "llegada_en", "atendida_en", "actualizado_en"])
    return cita


@transaction.atomic
def reprogramar(
    cita: Cita, nueva_fecha_hora: datetime, usuario=None, motivo_reprogramacion: str = ""
) -> Cita:
    """
    Marca la cita actual como reprogramada y crea una nueva con enlace
    a la original (`cita_origen`).
    """
    if cita.estado not in {Cita.Estado.RESERVADA, Cita.Estado.CONFIRMADA}:
        raise ValidationError("Solo se pueden reprogramar citas reservadas o confirmadas.")
    nueva = reservar_cita(
        expediente=cita.expediente,
        servicio=cita.servicio,
        profesional=cita.profesional,
        fecha_hora=nueva_fecha_hora,
        duracion_min=cita.duracion_min,
        motivo=cita.motivo,
        origen=cita.origen,
        usuario=usuario,
        cita_origen=cita,
    )
    cita.estado = Cita.Estado.REPROGRAMADA
    cita.observaciones = (
        cita.observaciones + "\n" if cita.observaciones else ""
    ) + f"Reprogramada: {motivo_reprogramacion}"
    cita.save(update_fields=["estado", "observaciones", "actualizado_en"])
    return nueva


@transaction.atomic
def cancelar(cita: Cita, motivo: str = "", usuario=None) -> Cita:
    """
    Cancela la cita y deja el motivo en las observaciones.

    El motivo se guarda EXPLÍCITAMENTE: `cambiar_estado` guarda con
    `update_fields` y `observaciones` no está en esa lista, así que asignarlo
    antes de llamarlo lo descartaba en silencio. Toda cancelación quedaba sin
    causa registrada.
    """
    if cita.estado not in {Cita.Estado.RESERVADA, Cita.Estado.CONFIRMADA, Cita.Estado.EN_ESPERA}:
        raise ValidationError("La cita no se puede cancelar en su estado actual.")
    cita.observaciones = (
        cita.observaciones + "\n" if cita.observaciones else ""
    ) + f"Cancelada: {motivo}"
    cita.save(update_fields=["observaciones", "actualizado_en"])
    return cambiar_estado(cita, Cita.Estado.CANCELADA, usuario=usuario)


# --------------------------------------------------------------- mi horario
#
# El profesional configura cuándo atiende y cuánto dura su consulta. Hasta
# ahora `Agenda` solo se tocaba desde el panel de administración de Django o
# desde el shell: quien atiende no podía declarar sus propios días ni cambiar
# la duración, que es justamente lo que decide los turnos que verá ventanilla.

# Una consulta de menos de cinco minutos no es una consulta, y una de más de
# cuatro horas no es un turno: son los mismos límites que ya validaba la API.
DURACION_MINIMA_MIN = 5
DURACION_MAXIMA_MIN = 240


def _franjas_que_chocan(profesional, dia_semana, hora_inicio, hora_fin, desde, hasta, excluir_pk):
    """
    Otras franjas del profesional que pisan a esta.

    Se miran TODOS sus servicios, no solo el de la franja: la persona es una y
    no puede estar el lunes a las 09:00 en Medicina y en Enfermería a la vez.
    Sin esta comprobación las dos pantallas ofrecían el mismo turno y la
    segunda reserva moría con «el turno ya está ocupado», que no explica nada.

    Solapan si los horarios se pisan Y las vigencias se pisan. El extremo
    derecho queda abierto: una franja puede empezar justo cuando acaba otra.
    """
    from django.db.models import Q

    candidatas = Agenda.objects.filter(
        profesional=profesional,
        dia_semana=dia_semana,
        activa=True,
        hora_inicio__lt=hora_fin,
        hora_fin__gt=hora_inicio,
    )
    if excluir_pk is not None:
        candidatas = candidatas.exclude(pk=excluir_pk)
    # Vigencias que se pisan: la otra no termina antes de que esta empiece, y
    # esta no termina antes de que la otra empiece.
    candidatas = candidatas.filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=desde))
    if hasta is not None:
        candidatas = candidatas.filter(vigente_desde__lte=hasta)
    return candidatas


@transaction.atomic
def guardar_franja(
    *,
    profesional: PerfilProfesional,
    servicio: Servicio,
    dia_semana: int,
    hora_inicio,
    hora_fin,
    duracion_turno_min: int,
    vigente_desde: date | None = None,
    vigente_hasta: date | None = None,
    franja: Agenda | None = None,
) -> Agenda:
    """
    Da de alta o actualiza una franja del horario del profesional.

    No decide nada por su cuenta: si el horario no cuadra, lo dice y no
    escribe. Las citas ya reservadas no se tocan —estrechar el horario no es
    cancelar a nadie—; de avisar de las que quedan fuera se encarga
    `citas_fuera_del_horario`.
    """
    if servicio.pk not in set(profesional.servicios.values_list("pk", flat=True)):
        raise ValidationError("No atiende en ese servicio, así que no puede darse horario en él.")

    if hora_inicio >= hora_fin:
        raise ValidationError("La hora de inicio tiene que ser anterior a la de fin.")

    if not DURACION_MINIMA_MIN <= duracion_turno_min <= DURACION_MAXIMA_MIN:
        raise ValidationError(
            f"La consulta dura entre {DURACION_MINIMA_MIN} y {DURACION_MAXIMA_MIN} minutos."
        )

    minutos = (hora_fin.hour * 60 + hora_fin.minute) - (hora_inicio.hour * 60 + hora_inicio.minute)
    if duracion_turno_min > minutos:
        # Sin esto la franja se guardaba y no producía ni un turno: la pantalla
        # decía «sin turnos disponibles» y no había manera de saber por qué.
        raise ValidationError(
            f"Una consulta de {duracion_turno_min} min no cabe en una franja de {minutos} min."
        )

    desde = vigente_desde or timezone.localdate()
    if vigente_hasta is not None and vigente_hasta < desde:
        raise ValidationError("La vigencia no puede terminar antes de empezar.")

    choques = _franjas_que_chocan(
        profesional,
        dia_semana,
        hora_inicio,
        hora_fin,
        desde,
        vigente_hasta,
        excluir_pk=franja.pk if franja else None,
    )
    otra = choques.select_related("servicio").first()
    if otra is not None:
        raise ValidationError(
            f"Se pisa con su franja de {otra.servicio.nombre} "
            f"({otra.hora_inicio:%H:%M}–{otra.hora_fin:%H:%M}) ese mismo día."
        )

    franja = franja or Agenda(profesional=profesional)
    franja.servicio = servicio
    franja.dia_semana = dia_semana
    franja.hora_inicio = hora_inicio
    franja.hora_fin = hora_fin
    franja.duracion_turno_min = duracion_turno_min
    franja.vigente_desde = desde
    franja.vigente_hasta = vigente_hasta
    franja.activa = True
    franja.save()
    return franja


@transaction.atomic
def retirar_franja(franja: Agenda) -> Agenda:
    """
    Deja de ofrecer turnos en esa franja.

    Se desactiva, no se borra: las citas ya reservadas apuntan al horario que
    regía cuando se reservaron, y borrar la franja dejaría el calendario sin
    forma de explicar de dónde salió una cita de las 09:20.
    """
    franja.activa = False
    franja.save(update_fields=["activa", "actualizado_en"])
    return franja
