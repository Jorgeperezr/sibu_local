"""
Pantallas de citas: control de acceso, reprogramación y cancelación.

`cambiar_estado_web` no comprobaba de quién era la cita: cualquier usuario
autenticado cambiaba el estado de cualquier cita conociendo su id, incluida
una de Psicología. Y `mi_agenda` dejaba ver la agenda de otro profesional con
`is_staff`, que es una bandera del panel de Django, no un rol de SIBU.

Reprogramar y cancelar existían en `services` desde el Sprint 3 sin ninguna
pantalla que llegara a ellos.
"""

from datetime import datetime, time, timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.citas import services
from apps.citas.models import Agenda, Cita
from apps.citas.tests.factories import _proximo_lunes
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


def _aware(fecha, hora):
    return timezone.make_aware(datetime.combine(fecha, hora), timezone.get_current_timezone())


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("medico_citas", est["medicina"], est["salud"])
    psicologo, perfil_psico = crear_profesional("psicologo_citas", est["psicologia"], est["psico"])
    otro, _ = crear_profesional("otro_medico_citas", est["medicina"], est["salud"])
    estudiante = Usuario.objects.create_user(
        username="estudiante_citas", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    for usuario in (medico, psicologo, otro, estudiante):
        usuario.set_password(CLAVE)
        usuario.save()

    lunes = _proximo_lunes()
    for perfil, servicio in ((perfil_medico, est["medicina"]), (perfil_psico, est["psicologia"])):
        Agenda.objects.create(
            profesional=perfil,
            servicio=servicio,
            dia_semana=0,
            hora_inicio=time(8, 0),
            hora_fin=time(12, 0),
            duracion_turno_min=20,
            vigente_desde=lunes - timedelta(days=1),
        )
    exp = crear_expediente(cedula="1104567894")
    cita = services.reservar_cita(
        expediente=exp,
        servicio=est["medicina"],
        profesional=perfil_medico,
        fecha_hora=_aware(lunes, time(9, 0)),
        motivo="Control",
    )
    cita_psico = services.reservar_cita(
        expediente=exp,
        servicio=est["psicologia"],
        profesional=perfil_psico,
        fecha_hora=_aware(lunes, time(10, 0)),
        motivo="Primera entrevista",
    )
    return {
        "est": est,
        "medico": medico,
        "psicologo": psicologo,
        "otro": otro,
        "estudiante": estudiante,
        "perfil_medico": perfil_medico,
        "exp": exp,
        "cita": cita,
        "cita_psico": cita_psico,
        "lunes": lunes,
    }


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------------- acceso


@pytest.mark.django_db
def test_un_estudiante_no_cambia_el_estado_de_una_cita(escenario):
    url = reverse("citas:cambiar_estado", args=[escenario["cita"].pk])
    respuesta = _cliente(escenario["estudiante"]).post(url, {"estado": Cita.Estado.CANCELADA})
    assert respuesta.status_code == 403
    escenario["cita"].refresh_from_db()
    assert escenario["cita"].estado == Cita.Estado.RESERVADA


@pytest.mark.django_db
def test_una_cita_de_psicologia_no_la_toca_quien_no_es_del_servicio(escenario):
    """
    El sello: la cita es del servicio confidencial. Ni el médico ni nadie de
    fuera la cancela, la reprograma ni le cambia el estado.
    """
    for nombre, datos in (
        ("citas:cambiar_estado", {"estado": Cita.Estado.CANCELADA}),
        ("citas:cancelar", {"motivo": "porque sí"}),
    ):
        url = reverse(nombre, args=[escenario["cita_psico"].pk])
        assert _cliente(escenario["medico"]).post(url, datos).status_code == 403
    escenario["cita_psico"].refresh_from_db()
    assert escenario["cita_psico"].estado == Cita.Estado.RESERVADA


@pytest.mark.django_db
def test_un_colega_del_mismo_servicio_si_puede(escenario):
    """La cita es de Medicina; otro médico cubre la agenda de un compañero."""
    url = reverse("citas:cambiar_estado", args=[escenario["cita"].pk])
    respuesta = _cliente(escenario["otro"]).post(url, {"estado": Cita.Estado.CONFIRMADA})
    assert respuesta.status_code == 302
    escenario["cita"].refresh_from_db()
    assert escenario["cita"].estado == Cita.Estado.CONFIRMADA


@pytest.mark.django_db
def test_la_agenda_ajena_no_se_ve_por_ser_del_panel_de_django(escenario):
    """
    Se abría con `is_staff`, una bandera del panel de administración de Django
    que no dice nada sobre el servicio. La agenda de Psicología lista nombres
    de pacientes y el motivo de cada cita.
    """
    escenario["estudiante"].is_staff = True
    escenario["estudiante"].save(update_fields=["is_staff"])
    respuesta = _cliente(escenario["estudiante"]).get(
        reverse("citas:mi_agenda"),
        {"profesional": escenario["cita_psico"].profesional_id, "fecha": escenario["lunes"]},
    )
    assert "Primera entrevista" not in respuesta.content.decode()


@pytest.mark.django_db
def test_el_profesional_ve_su_propia_agenda(escenario):
    respuesta = _cliente(escenario["medico"]).get(
        reverse("citas:mi_agenda"), {"fecha": escenario["lunes"]}
    )
    assert "Control" in respuesta.content.decode()


# ------------------------------------------------- reprogramar y cancelar


@pytest.mark.django_db
def test_cancelar_desde_la_agenda(escenario):
    url = reverse("citas:cancelar", args=[escenario["cita"].pk])
    _cliente(escenario["medico"]).post(url, {"motivo": "El paciente avisó que no puede"})
    escenario["cita"].refresh_from_db()
    assert escenario["cita"].estado == Cita.Estado.CANCELADA
    assert "El paciente avisó" in escenario["cita"].observaciones


@pytest.mark.django_db
def test_cancelar_exige_motivo(escenario):
    url = reverse("citas:cancelar", args=[escenario["cita"].pk])
    _cliente(escenario["medico"]).post(url, {"motivo": "  "}, follow=True)
    escenario["cita"].refresh_from_db()
    assert escenario["cita"].estado == Cita.Estado.RESERVADA


@pytest.mark.django_db
def test_reprogramar_desde_la_agenda(escenario):
    nueva = _aware(escenario["lunes"], time(11, 0))
    url = reverse("citas:reprogramar", args=[escenario["cita"].pk])
    _cliente(escenario["medico"]).post(
        url,
        {"fecha_hora": nueva.strftime("%Y-%m-%dT%H:%M"), "motivo": "Cruce con otra actividad"},
        follow=True,
    )
    escenario["cita"].refresh_from_db()
    assert escenario["cita"].estado == Cita.Estado.REPROGRAMADA
    reemplazo = Cita.objects.get(cita_origen=escenario["cita"])
    assert timezone.localtime(reemplazo.fecha_hora).hour == 11
    assert reemplazo.expediente_id == escenario["exp"].pk


@pytest.mark.django_db
def test_reprogramar_a_una_hora_ocupada_avisa_y_no_rompe_la_original(escenario):
    ocupada = services.reservar_cita(
        expediente=escenario["exp"],
        servicio=escenario["est"]["medicina"],
        profesional=escenario["perfil_medico"],
        fecha_hora=_aware(escenario["lunes"], time(11, 0)),
        motivo="Otra",
    )
    url = reverse("citas:reprogramar", args=[escenario["cita"].pk])
    respuesta = _cliente(escenario["medico"]).post(
        url,
        {
            "fecha_hora": timezone.localtime(ocupada.fecha_hora).strftime("%Y-%m-%dT%H:%M"),
            "motivo": "Cruce",
        },
        follow=True,
    )
    assert respuesta.status_code == 200
    escenario["cita"].refresh_from_db()
    assert escenario["cita"].estado == Cita.Estado.RESERVADA


@pytest.mark.django_db
def test_la_agenda_ofrece_reprogramar_y_cancelar(escenario):
    contenido = (
        _cliente(escenario["medico"])
        .get(reverse("citas:mi_agenda"), {"fecha": escenario["lunes"]})
        .content.decode()
    )
    assert reverse("citas:reprogramar", args=[escenario["cita"].pk]) in contenido
    assert reverse("citas:cancelar", args=[escenario["cita"].pk]) in contenido


@pytest.mark.django_db
def test_una_cita_ya_atendida_no_ofrece_reprogramarse(escenario):
    services.cambiar_estado(escenario["cita"], Cita.Estado.CONFIRMADA)
    services.cambiar_estado(escenario["cita"], Cita.Estado.EN_ESPERA)
    services.cambiar_estado(escenario["cita"], Cita.Estado.EN_ATENCION)
    services.cambiar_estado(escenario["cita"], Cita.Estado.ATENDIDA)
    contenido = (
        _cliente(escenario["medico"])
        .get(reverse("citas:mi_agenda"), {"fecha": escenario["lunes"]})
        .content.decode()
    )
    assert reverse("citas:reprogramar", args=[escenario["cita"].pk]) not in contenido


@pytest.mark.django_db
def test_no_se_vuelve_a_un_sitio_externo(escenario):
    """
    Se redirigía a `HTTP_REFERER` sin comprobarlo: la cabecera convertía estas
    vistas en un salto a cualquier dominio.
    """
    respuesta = _cliente(escenario["medico"]).post(
        reverse("citas:cambiar_estado", args=[escenario["cita"].pk]),
        {"estado": Cita.Estado.CONFIRMADA},
        HTTP_REFERER="https://sitio-ajeno.example/phishing",
    )
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("citas:mi_agenda")
