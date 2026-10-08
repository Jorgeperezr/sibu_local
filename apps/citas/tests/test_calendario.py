"""
El calendario del mes: ver de un vistazo dónde hay citas.

La agenda solo mostraba UN día, elegido en una casilla de fecha. Para saber si
el martes había consulta había que teclear el martes; para saber cuántas quedan
esta semana, cinco intentos. Y en la pantalla de reservar pasaba lo mismo al
revés: se elegía una fecha a ciegas y solo entonces aparecía —o no— un turno
libre.

El calendario responde a la pregunta que ninguna de las dos respondía: qué días
tienen algo. Lo que NO hace es enseñar contenido: por cada día da un conteo y
el nombre del servicio, nunca el paciente ni el motivo. Quien quiera el detalle
abre el día, y ahí manda el mismo control de siempre.
"""

from datetime import time, timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.citas import services
from apps.citas.models import Agenda
from apps.citas.selectors import conteo_por_dia
from apps.citas.tests.factories import _proximo_lunes
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


def _aware(fecha, hora):
    from datetime import datetime

    return timezone.make_aware(datetime.combine(fecha, hora), timezone.get_current_timezone())


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("med_cal", est["medicina"], est["salud"])
    psicologo, perfil_psico = crear_profesional("psi_cal", est["psicologia"], est["psico"])
    estudiante = Usuario.objects.create_user(
        username="est_cal", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    for usuario in (medico, psicologo, estudiante):
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
    # Dos citas el mismo lunes, para que el conteo diga 2 y no 1.
    for hora in (time(9, 0), time(9, 40)):
        services.reservar_cita(
            expediente=exp,
            servicio=est["medicina"],
            profesional=perfil_medico,
            fecha_hora=_aware(lunes, hora),
            motivo="Control de presión",
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
        "estudiante": estudiante,
        "perfil_medico": perfil_medico,
        "perfil_psico": perfil_psico,
        "lunes": lunes,
        "cita_psico": cita_psico,
    }


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------- el conteo


@pytest.mark.django_db
def test_cuenta_las_citas_de_cada_dia(escenario):
    conteo = conteo_por_dia(
        escenario["perfil_medico"], escenario["lunes"].year, escenario["lunes"].month
    )
    assert conteo[escenario["lunes"]] == 2


@pytest.mark.django_db
def test_los_dias_sin_citas_no_aparecen(escenario):
    """Un diccionario con 30 ceros haría el calendario más lento y no dice nada."""
    conteo = conteo_por_dia(
        escenario["perfil_medico"], escenario["lunes"].year, escenario["lunes"].month
    )
    assert all(n > 0 for n in conteo.values())
    assert escenario["lunes"] + timedelta(days=1) not in conteo


@pytest.mark.django_db
def test_no_mezcla_las_citas_de_otro_profesional(escenario):
    conteo = conteo_por_dia(
        escenario["perfil_psico"], escenario["lunes"].year, escenario["lunes"].month
    )
    assert conteo[escenario["lunes"]] == 1


@pytest.mark.django_db
def test_una_cita_cancelada_no_ocupa_el_calendario(escenario):
    """
    El calendario dice dónde hay trabajo. Una cancelada no lo es, y contarla
    haría parecer lleno un día libre.
    """
    from apps.citas.models import Cita

    cita = Cita.objects.filter(profesional=escenario["perfil_medico"]).first()
    services.cancelar(cita, motivo="El paciente avisó", usuario=escenario["medico"])

    conteo = conteo_por_dia(
        escenario["perfil_medico"], escenario["lunes"].year, escenario["lunes"].month
    )
    assert conteo[escenario["lunes"]] == 1


# ------------------------------------------------------------- la pantalla


@pytest.mark.django_db
def test_la_pantalla_pinta_el_mes_y_marca_los_dias_con_citas(escenario):
    respuesta = _cliente(escenario["medico"]).get(
        reverse("citas:calendario"),
        {"anio": escenario["lunes"].year, "mes": escenario["lunes"].month},
    )
    assert respuesta.status_code == 200
    contenido = respuesta.content.decode()
    assert "Lun" in contenido and "Dom" in contenido
    semanas = respuesta.context["semanas"]
    dias = [d for semana in semanas for d in semana if d["fecha"] == escenario["lunes"]]
    assert dias and dias[0]["citas"] == 2


@pytest.mark.django_db
def test_cada_dia_enlaza_a_su_agenda(escenario):
    """El calendario sitúa; el detalle sigue viviendo en la agenda del día."""
    contenido = (
        _cliente(escenario["medico"])
        .get(
            reverse("citas:calendario"),
            {"anio": escenario["lunes"].year, "mes": escenario["lunes"].month},
        )
        .content.decode()
    )
    assert f"fecha={escenario['lunes'].isoformat()}" in contenido


@pytest.mark.django_db
def test_se_navega_al_mes_anterior_y_al_siguiente(escenario):
    """Sin enlaces, ver diciembre desde enero exige editar la URL a mano."""
    contenido = (
        _cliente(escenario["medico"]).get(reverse("citas:calendario"), {"anio": 2026, "mes": 1})
    ).content.decode()
    assert "anio=2025&amp;mes=12" in contenido or "anio=2025&mes=12" in contenido
    assert "anio=2026&amp;mes=2" in contenido or "anio=2026&mes=2" in contenido


@pytest.mark.django_db
def test_un_mes_imposible_no_revienta(escenario):
    """`?mes=13` es un parámetro de URL: llega lo que sea."""
    for parametros in ({"mes": 13}, {"mes": 0}, {"anio": "ayer"}, {"mes": "x", "anio": "y"}):
        assert (
            _cliente(escenario["medico"]).get(reverse("citas:calendario"), parametros).status_code
            == 200
        )


# ------------------------------------------------------------------ el sello


@pytest.mark.django_db
def test_el_calendario_no_enseña_ni_paciente_ni_motivo(escenario):
    """
    Da conteos, no contenido. Un calendario que imprimiera el nombre haría
    innecesario abrir el día —y saltaría el control que vive en la agenda—.
    """
    contenido = (
        _cliente(escenario["medico"])
        .get(
            reverse("citas:calendario"),
            {"anio": escenario["lunes"].year, "mes": escenario["lunes"].month},
        )
        .content.decode()
    )
    assert "Control de presión" not in contenido
    assert "Paciente" not in contenido or "paciente" not in contenido.lower().split("hora")[0]


@pytest.mark.django_db
def test_no_se_mira_el_calendario_de_un_profesional_de_otro_servicio(escenario):
    """
    Mismo control que `mi_agenda`: ver la carga de otro exige compartir
    servicio con él. Sobre Psicología, el conteo por día ya dice cuántos
    pacientes ve y cuándo.
    """
    respuesta = _cliente(escenario["medico"]).get(
        reverse("citas:calendario"), {"profesional": escenario["perfil_psico"].pk}
    )
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_un_estudiante_no_abre_el_calendario(escenario):
    assert _cliente(escenario["estudiante"]).get(reverse("citas:calendario")).status_code == 403
