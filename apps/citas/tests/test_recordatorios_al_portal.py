"""
Un recordatorio de cita tiene que llegarle a alguien.

`enviar_recordatorios` creaba la notificación con `destinatario_correo` y
`destinatario_nombre`, pero sin `usuario`. Cuando la persona no tiene correo
institucional el canal queda `IN_APP` —una notificación dentro de la
aplicación— dirigida a ningún usuario de la aplicación: no aparece en la
bandeja de nadie y el correo tampoco sale. El recordatorio no llega.

Si el paciente tiene cuenta del portal vinculada y verificada, esa es su
identidad dentro del sistema y ahí debe ir.
"""

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.citas import services
from apps.citas.models import Agenda
from apps.citas.tasks import enviar_recordatorios
from apps.citas.tests.factories import _proximo_lunes
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.notificaciones.models import Notificacion
from apps.portal.models import VinculacionPortal
from apps.usuarios.models import Rol, Usuario


def _aware(fecha, hora):
    from datetime import datetime

    return timezone.make_aware(datetime.combine(fecha, hora), timezone.get_current_timezone())


@pytest.fixture
def cita_manana(db):
    est = crear_estructura()
    _, perfil = crear_profesional("med_rec", est["medicina"], est["salud"])
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
    expediente = crear_expediente()
    cita = services.reservar_cita(
        expediente=expediente,
        servicio=est["medicina"],
        profesional=perfil,
        fecha_hora=_aware(lunes, time(9, 0)),
        motivo="Control",
    )
    return {"expediente": expediente, "cita": cita}


@pytest.mark.django_db
def test_el_recordatorio_llega_a_la_cuenta_del_portal(cita_manana, monkeypatch):
    paciente = Usuario.objects.create_user(
        username="paciente_portal", password="x", rol_principal=Rol.USUARIO_FINAL
    )
    VinculacionPortal.objects.create(
        usuario=paciente,
        expediente=cita_manana["expediente"],
        verificado=True,
        correo_destino="p@unl.edu.ec",
        token_hash="x",
        token_expira_en=timezone.now() + timedelta(hours=1),
    )
    # La ventana del recordatorio se calcula desde ahora; se apunta a la cita.
    horas = int((cita_manana["cita"].fecha_hora - timezone.now()).total_seconds() // 3600)
    enviar_recordatorios(horas=horas, tolerancia_minutos=120)

    aviso = Notificacion.objects.filter(referencia_tipo="Cita").first()
    assert aviso is not None, "no se creó ningún recordatorio"
    assert aviso.usuario == paciente, "el recordatorio no le llegó a nadie"


@pytest.mark.django_db
def test_sin_cuenta_vinculada_el_recordatorio_sigue_saliendo_por_correo(cita_manana):
    """
    No todo el mundo tiene cuenta del portal. Sin ella el aviso sigue teniendo
    destinatario de correo, que es como llegaba antes.
    """
    horas = int((cita_manana["cita"].fecha_hora - timezone.now()).total_seconds() // 3600)
    enviar_recordatorios(horas=horas, tolerancia_minutos=120)

    aviso = Notificacion.objects.filter(referencia_tipo="Cita").first()
    assert aviso is not None
    assert aviso.usuario is None
    assert aviso.destinatario_nombre
