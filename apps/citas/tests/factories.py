"""Factories para pruebas de citas."""

from datetime import date, time, timedelta

from django.utils import timezone

from apps.citas.models import Agenda
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional


def escenario_basico():
    """Estructura + profesional de medicina + expediente + agenda de lunes."""
    est = crear_estructura()
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567894")
    lunes_proximo = _proximo_lunes()
    agenda = Agenda.objects.create(
        profesional=medico,
        servicio=est["medicina"],
        dia_semana=0,
        hora_inicio=time(8, 0),
        hora_fin=time(12, 0),
        duracion_turno_min=20,
        vigente_desde=lunes_proximo - timedelta(days=1),
    )
    return {"est": est, "medico": medico, "exp": exp, "agenda": agenda, "lunes": lunes_proximo}


def _proximo_lunes() -> date:
    hoy = timezone.localdate()
    return hoy + timedelta(days=(7 - hoy.weekday()) % 7 or 7)
