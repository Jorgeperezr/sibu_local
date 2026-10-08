"""Consultas de lectura de citas y agendas."""

from datetime import date, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.usuarios.models import PerfilProfesional

from .models import Cita
from .services import ESTADOS_ACTIVOS

# Tolerancia por defecto de la ventana del recordatorio.
# 15 min corresponde a la frecuencia recomendada de ejecución del task en
# Celery Beat: cada tick abarca exactamente una ventana sin solapamiento.
TOLERANCIA_MINUTOS_DEFECTO = 15


def citas_del_dia(profesional: PerfilProfesional, fecha: date | None = None):
    fecha = fecha or timezone.localdate()
    return (
        Cita.objects.filter(profesional=profesional, fecha_hora__date=fecha)
        .select_related("expediente__persona", "servicio")
        .order_by("fecha_hora")
    )


def conteo_por_dia(profesional: PerfilProfesional, anio: int, mes: int) -> dict[date, int]:
    """
    Cuántas citas VIVAS tiene el profesional cada día de un mes.

    Una consulta agregada, no una por día: un calendario que preguntara 31
    veces sería el N+1 que ninguna otra pantalla tiene.

    Cuenta solo los estados activos. Una cita cancelada no es trabajo, y
    contarla haría parecer lleno un día libre —que es justo lo contrario de lo
    que un calendario viene a decir—.

    Devuelve solo los días con algo: treinta ceros ocupan sitio y no informan.
    """
    filas = (
        Cita.objects.filter(
            profesional=profesional,
            estado__in=ESTADOS_ACTIVOS,
            fecha_hora__year=anio,
            fecha_hora__month=mes,
        )
        .annotate(dia=TruncDate("fecha_hora"))
        .values("dia")
        .annotate(n=Count("id"))
    )
    return {fila["dia"]: fila["n"] for fila in filas}


def proximas_del_expediente(expediente, limite=5):
    return (
        Cita.objects.filter(
            expediente=expediente,
            estado__in=ESTADOS_ACTIVOS,
            fecha_hora__gte=timezone.now(),
        )
        .select_related("servicio", "profesional__usuario")
        .order_by("fecha_hora")[:limite]
    )


def citas_para_recordatorio(horas_anticipacion: int, tolerancia_minutos: int | None = None):
    """
    Devuelve citas cuya `fecha_hora` está a ~`horas_anticipacion` horas de ahora,
    dentro de una ventana de ±`tolerancia_minutos`.

    - En producción el task se programa cada 15 min con la tolerancia por
      defecto (15 min): cada cita cae en exactamente una ventana → sin
      duplicados y sin omisiones.
    - Para ejecuciones manuales o pruebas puede ampliarse la tolerancia.

    Estados considerados: RESERVADA y CONFIRMADA (fuente del recordatorio
    T-48h/T-24h, informe 5.2 M17).
    """
    tolerancia = (
        tolerancia_minutos if tolerancia_minutos is not None else TOLERANCIA_MINUTOS_DEFECTO
    )
    ahora = timezone.now()
    centro = ahora + timedelta(hours=horas_anticipacion)
    inicio = centro - timedelta(minutes=tolerancia)
    fin = centro + timedelta(minutes=tolerancia)
    return Cita.objects.filter(
        fecha_hora__range=(inicio, fin),
        estado__in={Cita.Estado.RESERVADA, Cita.Estado.CONFIRMADA},
    ).select_related("expediente__persona", "servicio")


def citas_visibles(user, queryset):
    """
    Filtra un queryset de Cita según quién pregunta.

    Una cita no es contenido clínico, pero lleva el nombre del paciente, su
    cédula, el servicio y el motivo. Sobre un servicio confidencial eso es el
    padrón del servicio: saber que alguien tiene hora con Psicología ya dice
    que es paciente de Psicología.

    Dos reglas, en este orden:

    1. **Hay que ser personal de la Unidad.** `puede_ver_expediente` es el
       mismo gate que usan las pantallas del expediente: deja fuera al rol
       USUARIO_FINAL, que es la cuenta de un estudiante. Su propia agenda la
       ve por el portal, que aísla por identidad.
    2. **Lo confidencial, solo su servicio.** Ni Dirección, ni Coordinación,
       ni ventanilla, ni administración. Es la regla que ya aplican
       `rbac.puede_ver_atencion` y la pantalla `mi_agenda`.

    No se filtra por servicio propio más allá de eso, y es deliberado: quien
    reserva en ventanilla tiene rol ADMINISTRATIVO y ningún servicio asignado,
    así que hacerlo le dejaría la pantalla vacía y rompería el trabajo que esta
    consulta existe para hacer.
    """
    from apps.usuarios.rbac import (
        SERVICIOS_CONFIDENCIALES,
        puede_ver_expediente,
        servicios_del_usuario,
    )

    if not user.is_authenticated or not puede_ver_expediente(user):
        return queryset.none()
    mis_servicios = servicios_del_usuario(user)
    return queryset.exclude(
        servicio__codigo__in=SERVICIOS_CONFIDENCIALES,
    ) | queryset.filter(servicio_id__in=mis_servicios)


def franjas_del_profesional(profesional: PerfilProfesional):
    """
    El horario configurado, incluidas las franjas retiradas.

    Las retiradas se conservan porque explican de dónde salió una cita ya
    reservada; la pantalla las enseña aparte.
    """
    from .models import Agenda

    return (
        Agenda.objects.filter(profesional=profesional)
        .select_related("servicio")
        # Las vigentes primero: el horario que rige es lo que se viene a ver, y
        # las retiradas están para explicar una cita antigua, no para encabezar.
        .order_by("-activa", "dia_semana", "hora_inicio")
    )


def citas_fuera_del_horario(profesional: PerfilProfesional):
    """
    Citas vivas y futuras que ya no caen dentro de ninguna franja vigente.

    Estrechar el horario o retirar un día NO cancela a nadie: quien reservó un
    jueves a las 16:00 sigue teniendo su hora, y decidir qué hacer con ella es
    del profesional, no del sistema. Lo que sí hace el sistema es no callárselo:
    sin este aviso la cita desaparecía de los turnos ofrecidos y seguía viva en
    la agenda del día, y el paciente se presentaba a una consulta que su
    profesional ya no tenía prevista.

    Se miran solo las futuras: una cita pasada se atendió o no, y reprocharla
    ahora no arregla nada.
    """
    from .services import agendas_vigentes

    candidatas = (
        Cita.objects.filter(
            profesional=profesional,
            estado__in=ESTADOS_ACTIVOS,
            fecha_hora__gte=timezone.now(),
        )
        .select_related("expediente__persona", "servicio")
        .order_by("fecha_hora")
    )

    fuera = []
    for cita in candidatas:
        local = timezone.localtime(cita.fecha_hora)
        fin = timezone.localtime(cita.fin)
        cabe = agendas_vigentes(profesional, local.date(), cita.servicio).filter(
            hora_inicio__lte=local.time(), hora_fin__gte=fin.time()
        )
        if fin.date() != local.date() or not cabe.exists():
            fuera.append(cita)
    return fuera
