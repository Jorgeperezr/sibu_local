"""
El recordatorio de cita no llegaba nunca a nadie.

Estaba escrito como task de Celery (`enviar_recordatorios`), con pruebas que lo
ejercitaban a mano. Pero el planificador configurado es el de base de datos
—`django_celery_beat.schedulers:DatabaseScheduler`— y **el código no crea
ninguna fila de `PeriodicTask`**: nadie lo dispara. Ni en un servidor ni, menos
aún, en una portable, que no tiene demonio detrás.

Y la ventana del task tampoco servía para una portable: ±15 minutos alrededor
de T-48h es lo correcto para un planificador que corre cada cuarto de hora, y
es inútil para un programa que se abre a cualquier hora. La cita tendría que
caer justo en esa media hora.

De ahí `recordatorios_pendientes`: el repaso de los que ya tocaba enviar y
nadie envió. La portable lo corre al arrancar.
"""

from datetime import time, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.citas import services
from apps.citas.models import Agenda, Cita
from apps.citas.tests.factories import _proximo_lunes
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.notificaciones.models import Notificacion


def _cita_en(horas: float, cedula="1104567894"):
    """Una cita reservada a `horas` de ahora."""
    est = crear_estructura()
    _, perfil = crear_profesional("med_pend", est["medicina"], est["salud"])
    lunes = _proximo_lunes()
    Agenda.objects.create(
        profesional=perfil,
        servicio=est["medicina"],
        dia_semana=0,
        hora_inicio=time(8, 0),
        hora_fin=time(12, 0),
        duracion_turno_min=20,
        vigente_desde=lunes - timedelta(days=1),
    )
    cita = Cita.objects.create(
        expediente=crear_expediente(cedula=cedula),
        servicio=est["medicina"],
        profesional=perfil,
        fecha_hora=timezone.now() + timedelta(hours=horas),
        duracion_min=20,
        estado=Cita.Estado.RESERVADA,
    )
    return cita


@pytest.mark.django_db
def test_una_cita_a_treinta_horas_tiene_recordatorio_pendiente():
    """
    Lo que no hacía nadie. A 30 horas de la cita, el aviso de 48 ya venció y
    la ventana de ±15 min del task no lo habría encontrado jamás.
    """
    cita = _cita_en(30)

    assert services.recordatorios_pendientes() == 1
    assert Notificacion.objects.filter(referencia_id=cita.id).count() == 1


@pytest.mark.django_db
def test_el_titulo_dice_las_horas_que_faltan_no_las_de_la_ventana():
    """
    Una cita a 25 horas cae en la ventana de 48 —es la que no se ha enviado—.
    Anunciarla como «en 48h» le adelanta la cita un día entero a quien la lee.
    """
    _cita_en(25)

    services.recordatorios_pendientes()
    aviso = Notificacion.objects.get()

    assert aviso.tipo == "recordatorio_cita_48h", "la ventana vencida es la de 48"
    assert "48h" not in aviso.titulo, f"el título miente: {aviso.titulo!r}"
    assert "25h" in aviso.titulo


@pytest.mark.django_db
def test_a_veinte_horas_le_toca_la_ventana_de_veinticuatro():
    """
    Se elige la ventana vencida más próxima, una sola. Crear también la de 48
    a 20 horas de la cita no es un recordatorio tardío: es una fecha errónea.
    """
    _cita_en(20)

    assert services.recordatorios_pendientes() == 1
    assert Notificacion.objects.get().tipo == "recordatorio_cita_24h"


@pytest.mark.django_db
def test_correr_dos_veces_no_duplica():
    """De esto depende poder llamarlo en cada arranque de la portable."""
    _cita_en(30)

    assert services.recordatorios_pendientes() == 1
    assert services.recordatorios_pendientes() == 0
    assert Notificacion.objects.count() == 1


@pytest.mark.django_db
def test_una_cita_lejana_todavia_no_toca():
    """A 60 horas no ha vencido ninguna ventana: avisar ahora es ruido."""
    _cita_en(60)

    assert services.recordatorios_pendientes() == 0
    assert not Notificacion.objects.exists()


@pytest.mark.django_db
def test_una_cita_cancelada_no_se_recuerda():
    cita = _cita_en(30)
    cita.estado = Cita.Estado.CANCELADA
    cita.save(update_fields=["estado"])

    assert services.recordatorios_pendientes() == 0


@pytest.mark.django_db
def test_una_cita_pasada_no_se_recuerda():
    """Un recordatorio de algo que ya ocurrió solo confunde."""
    _cita_en(-5)

    assert services.recordatorios_pendientes() == 0


@pytest.mark.django_db
def test_la_fecha_del_mensaje_va_en_hora_de_loja():
    """
    El mensaje lleva la hora a la que la persona tiene que presentarse. Sin
    `localtime`, un servidor en UTC la corre cinco horas.
    """
    cita = _cita_en(30)

    services.recordatorios_pendientes()
    esperada = timezone.localtime(cita.fecha_hora).strftime("%d/%m/%Y a las %H:%M")

    assert esperada in Notificacion.objects.get().mensaje


@pytest.mark.django_db
def test_el_comando_existe_y_es_el_que_corre_la_portable():
    """
    `arrancar.py` lo llama en cada arranque: si el comando no existe, la
    portable no levanta.
    """
    _cita_en(30)

    call_command("recordatorios", "--silencioso", verbosity=0)

    assert Notificacion.objects.count() == 1
