"""Prueba del task de recordatorios."""

import pytest
from freezegun import freeze_time

from apps.citas import services
from apps.citas.tasks import enviar_recordatorios
from apps.citas.tests.factories import escenario_basico
from apps.notificaciones.models import Notificacion


@pytest.mark.django_db
def test_enviar_recordatorios_evita_duplicados():
    """
    Con el reloj congelado a domingo 08:00 hora local, la cita del próximo
    lunes 08:00 queda exactamente a T+24h y cae en la ventana ±15min.
    La segunda ejecución no debe duplicar la notificación.
    """
    with freeze_time("2026-01-04 13:00:00"):
        e = escenario_basico()
        e["exp"].persona.correo_institucional = "test@unl.edu.ec"
        e["exp"].persona.save()
        turnos = services.turnos_disponibles(e["medico"], e["est"]["medicina"], e["lunes"])
        assert turnos
        services.reservar_cita(
            expediente=e["exp"],
            servicio=e["est"]["medicina"],
            profesional=e["medico"],
            fecha_hora=turnos[0],
        )
        assert enviar_recordatorios(24) == 1
        assert enviar_recordatorios(24) == 0  # idempotencia
        assert Notificacion.objects.count() == 1
