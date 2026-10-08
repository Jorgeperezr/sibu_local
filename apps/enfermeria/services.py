"""Lógica de negocio de Enfermería."""

from datetime import date, timedelta

from django.utils import timezone

from apps.expediente.models import Expediente

from .models import SignosVitales


def signos_del_dia(expediente: Expediente, fecha: date | None = None):
    """
    Devuelve todos los signos vitales tomados hoy (o en la fecha dada) al
    expediente, ordenados del más reciente al más antiguo. Este es el punto
    de reutilización para Medicina: al abrir una HC, se muestra el último
    triaje si existe.
    """
    fecha = fecha or timezone.localdate()
    return SignosVitales.objects.filter(expediente=expediente, fecha_hora__date=fecha).order_by(
        "-fecha_hora"
    )


def triajes_del_dia(fecha: date | None = None):
    """
    Todos los signos vitales tomados hoy (o en la fecha dada), de cualquier
    expediente: la cola de trabajo del servicio.

    `timezone.localdate()` y no `date.today()`: en America/Guayaquil (UTC-5) la
    fecha UTC va adelantada cinco horas y los triajes de la tarde caerían en el
    día siguiente.
    """
    fecha = fecha or timezone.localdate()
    return (
        SignosVitales.objects.filter(fecha_hora__date=fecha)
        .select_related("expediente__persona", "responsable__usuario")
        .order_by("-fecha_hora")
    )


def ultimo_triaje(expediente: Expediente, horas_maximo: int = 12):
    """
    Último registro de signos vitales del expediente en las últimas N horas
    (por defecto 12), o None si no hay reciente. Usado por Medicina para
    heredar los signos del triaje.
    """
    corte = timezone.now() - timedelta(hours=horas_maximo)
    return (
        SignosVitales.objects.filter(expediente=expediente, fecha_hora__gte=corte)
        .order_by("-fecha_hora")
        .first()
    )
