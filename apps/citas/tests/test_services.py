"""Pruebas de la lógica de negocio de citas."""

from datetime import datetime, time

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.citas import services
from apps.citas.models import BloqueoAgenda, Cita
from apps.citas.selectors import citas_del_dia, citas_para_recordatorio, proximas_del_expediente
from apps.citas.tests.factories import escenario_basico


def _hora(fecha, h, m=0):
    tz = timezone.get_current_timezone()
    return datetime.combine(fecha, time(h, m), tzinfo=tz)


@pytest.mark.django_db
def test_turnos_disponibles_respeta_agenda():
    e = escenario_basico()
    turnos = services.turnos_disponibles(e["medico"], e["est"]["medicina"], e["lunes"])
    # 8:00 a 12:00 en pasos de 20 min = 12 turnos
    assert len(turnos) == 12
    assert turnos[0].hour == 8 and turnos[0].minute == 0
    assert turnos[-1].hour == 11 and turnos[-1].minute == 40


@pytest.mark.django_db
def test_reservar_cita_ocupa_turno():
    e = escenario_basico()
    inicio = _hora(e["lunes"], 9, 0)
    services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=inicio,
        duracion_min=20,
    )
    turnos = services.turnos_disponibles(e["medico"], e["est"]["medicina"], e["lunes"])
    assert inicio not in turnos
    assert len(turnos) == 11


@pytest.mark.django_db
def test_reservar_conflicto_lanza_error():
    e = escenario_basico()
    inicio = _hora(e["lunes"], 9, 0)
    services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=inicio,
    )
    with pytest.raises(ValidationError):
        services.reservar_cita(
            expediente=e["exp"],
            servicio=e["est"]["medicina"],
            profesional=e["medico"],
            fecha_hora=inicio,
        )


@pytest.mark.django_db
def test_reservar_fuera_de_agenda():
    e = escenario_basico()
    with pytest.raises(ValidationError):
        services.reservar_cita(
            expediente=e["exp"],
            servicio=e["est"]["medicina"],
            profesional=e["medico"],
            fecha_hora=_hora(e["lunes"], 15, 0),  # tarde
        )


@pytest.mark.django_db
def test_reservar_en_bloqueo():
    e = escenario_basico()
    BloqueoAgenda.objects.create(
        profesional=e["medico"],
        fecha_inicio=_hora(e["lunes"], 9, 0),
        fecha_fin=_hora(e["lunes"], 10, 0),
        motivo="Reunión de coordinación",
    )
    with pytest.raises(ValidationError):
        services.reservar_cita(
            expediente=e["exp"],
            servicio=e["est"]["medicina"],
            profesional=e["medico"],
            fecha_hora=_hora(e["lunes"], 9, 20),
        )


@pytest.mark.django_db
def test_maquina_de_estados_transicion_valida():
    e = escenario_basico()
    cita = services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 0),
    )
    services.cambiar_estado(cita, Cita.Estado.CONFIRMADA)
    services.cambiar_estado(cita, Cita.Estado.EN_ESPERA)
    assert cita.llegada_en is not None
    services.cambiar_estado(cita, Cita.Estado.EN_ATENCION)
    services.cambiar_estado(cita, Cita.Estado.ATENDIDA)
    assert cita.atendida_en is not None


@pytest.mark.django_db
def test_transicion_invalida_lanza_error():
    e = escenario_basico()
    cita = services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 0),
    )
    with pytest.raises(ValidationError):
        services.cambiar_estado(cita, Cita.Estado.ATENDIDA)  # sin pasar por atención


@pytest.mark.django_db
def test_reprogramar_enlaza_nueva_con_anterior():
    e = escenario_basico()
    cita = services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 0),
    )
    nueva = services.reprogramar(
        cita, _hora(e["lunes"], 10, 0), motivo_reprogramacion="Cambio pedido por el paciente"
    )
    cita.refresh_from_db()
    assert cita.estado == Cita.Estado.REPROGRAMADA
    assert nueva.cita_origen_id == cita.id
    assert "Reprogramada" in cita.observaciones


@pytest.mark.django_db
def test_cancelar_solo_permitido_en_estados_previos():
    e = escenario_basico()
    cita = services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 0),
    )
    services.cambiar_estado(cita, Cita.Estado.CONFIRMADA)
    services.cambiar_estado(cita, Cita.Estado.EN_ESPERA)
    services.cambiar_estado(cita, Cita.Estado.EN_ATENCION)
    with pytest.raises(ValidationError):
        services.cancelar(cita, motivo="tardío")


@pytest.mark.django_db
def test_selectors_del_dia_y_proximas():
    e = escenario_basico()
    services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 0),
    )
    services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 10, 0),
    )
    assert citas_del_dia(e["medico"], e["lunes"]).count() == 2
    assert proximas_del_expediente(e["exp"]).count() == 2


@pytest.mark.django_db
def test_recordatorio_ventana_temporal():
    """
    El selector de recordatorios (±15 min por defecto) encuentra una cita
    a T-24h.

    Se congela el tiempo con freezegun a un domingo 08:00 local para que
    el próximo lunes 08:00 quede exactamente a 24h de "ahora" y caiga en
    la ventana. Esto hace el test determinista, sin depender del día en
    que se ejecute la suite.
    """
    from freezegun import freeze_time

    # 2026-01-04 13:00 UTC == 2026-01-04 08:00 America/Guayaquil (domingo)
    with freeze_time("2026-01-04 13:00:00"):
        e = escenario_basico()
        turnos = services.turnos_disponibles(e["medico"], e["est"]["medicina"], e["lunes"])
        assert turnos, "El escenario debe generar turnos el próximo lunes"
        turno = turnos[0]  # lunes 08:00 = T+24h exacto
        services.reservar_cita(
            expediente=e["exp"],
            servicio=e["est"]["medicina"],
            profesional=e["medico"],
            fecha_hora=turno,
        )
        encontradas = citas_para_recordatorio(horas_anticipacion=24)
        assert encontradas.count() == 1


@pytest.mark.django_db
def test_recordatorio_con_tolerancia_ampliada():
    """La tolerancia configurable permite ventanas más amplias en ejecuciones manuales."""
    from freezegun import freeze_time

    with freeze_time("2026-01-04 13:00:00"):
        e = escenario_basico()
        turnos = services.turnos_disponibles(e["medico"], e["est"]["medicina"], e["lunes"])
        turno = turnos[3]  # lunes 09:00 = T+25h → fuera de ventana ±15min
        services.reservar_cita(
            expediente=e["exp"],
            servicio=e["est"]["medicina"],
            profesional=e["medico"],
            fecha_hora=turno,
        )
        # Ventana por defecto (±15 min): no la encuentra
        assert citas_para_recordatorio(24).count() == 0
        # Tolerancia de 90 min: sí la encuentra
        assert citas_para_recordatorio(24, tolerancia_minutos=90).count() == 1


@pytest.mark.django_db
def test_una_cita_no_puede_solaparse_con_otra_aunque_empiece_a_otra_hora():
    """
    La restricción única de BD solo ve la hora de inicio exacta.

    Una cita de 9:00 con 40 minutos y otra de 9:20 no coinciden en `fecha_hora`,
    así que entraban las dos y el profesional se quedaba con dos pacientes a la
    misma hora. Ahora se comparan los intervalos.
    """
    e = escenario_basico()
    services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 0),
        duracion_min=40,
    )
    with pytest.raises(ValidationError, match="ocupado"):
        services.reservar_cita(
            expediente=e["exp"],
            servicio=e["est"]["medicina"],
            profesional=e["medico"],
            fecha_hora=_hora(e["lunes"], 9, 20),
            duracion_min=20,
        )


@pytest.mark.django_db
def test_una_cita_puede_empezar_justo_cuando_termina_la_anterior():
    """El extremo derecho es abierto: a las 9:20 en punto la agenda está libre."""
    e = escenario_basico()
    services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 0),
        duracion_min=20,
    )
    cita = services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 20),
        duracion_min=20,
    )
    assert cita.pk is not None


@pytest.mark.django_db
def test_una_cita_cancelada_libera_su_intervalo():
    """Solo ocupan agenda los estados activos."""
    e = escenario_basico()
    primera = services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 0),
        duracion_min=40,
    )
    services.cambiar_estado(primera, Cita.Estado.CANCELADA)
    cita = services.reservar_cita(
        expediente=e["exp"],
        servicio=e["est"]["medicina"],
        profesional=e["medico"],
        fecha_hora=_hora(e["lunes"], 9, 20),
        duracion_min=20,
    )
    assert cita.pk is not None
