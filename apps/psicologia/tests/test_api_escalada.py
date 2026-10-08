"""
Abrir un proceso psicológico desde fuera era una escalada al servicio sellado.

`services.crear_ficha` nunca comprobó que el profesional fuera de Psicología, y
el endpoint tampoco: `FichaPsicologicaViewSet.create` solo exigía tener perfil.
Con eso, un médico —cualquier profesional con perfil— abría un proceso
psicológico sobre el expediente de quien quisiera.

Lo grave no es el proceso vacío que queda: es lo que abre después.
`rbac.puede_ver_atencion` concede acceso al TRATANTE antes de mirar si el
servicio es confidencial —«el propio profesional que la realizó siempre puede
verla»—, así que quien se nombra tratante entra al servicio sellado por la
puerta principal: lee la ficha, registra sesiones y aplica escalas.

La pantalla web ya lo impedía con `verificar_es_del_servicio`. La API no.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.psicologia import services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("med_esc", est["medicina"], est["salud"])
    psicologo, perfil_psico = crear_profesional("psi_esc", est["psicologia"], est["psico"])
    for usuario in (medico, psicologo):
        usuario.set_password(CLAVE)
        usuario.save()
    return {
        "est": est,
        "medico": medico,
        "perfil_medico": perfil_medico,
        "psicologo": psicologo,
        "perfil_psico": perfil_psico,
        "expediente": crear_expediente(),
    }


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


@pytest.mark.django_db
def test_el_servicio_rechaza_a_un_profesional_de_otro_servicio(escenario):
    """
    La comprobación va en el servicio y no solo en el endpoint: es la capa por
    la que pasan la pantalla, la API y cualquier cosa que se escriba mañana.
    """
    with pytest.raises(ValidationError, match="Psicología"):
        services.crear_ficha(
            expediente=escenario["expediente"],
            profesional=escenario["perfil_medico"],
            motivo="Sospecha de depresión",
        )


@pytest.mark.django_db
def test_el_endpoint_no_deja_a_un_medico_abrir_un_proceso(escenario):
    respuesta = _cliente(escenario["medico"]).post(
        "/api/v1/psicologia/fichas/",
        {"expediente": escenario["expediente"].pk, "motivo": "x", "modalidad": "presencial"},
        content_type="application/json",
    )
    assert respuesta.status_code in (400, 403), respuesta.content
    from apps.psicologia.models import FichaPsicologica

    assert not FichaPsicologica.objects.exists()


@pytest.mark.django_db
def test_sin_esto_el_medico_quedaba_de_tratante_y_entraba_a_leer(escenario):
    """
    La escalada completa, fijada de una pieza: si el proceso llegara a
    abrirse con un médico de tratante, `puede_ver_atencion` le daría acceso
    al contenido sellado por ser quien lo realizó.

    Se comprueba sobre una ficha legítima de Psicología: el médico no la ve.
    Lo que impide la otra mitad —que se nombre tratante— es la prueba de
    arriba; juntas cierran el camino entero.
    """
    from apps.usuarios import rbac

    ficha = services.crear_ficha(
        expediente=escenario["expediente"],
        profesional=escenario["perfil_psico"],
        motivo="Primera entrevista",
    )
    assert rbac.puede_ver_atencion(escenario["medico"], ficha.atencion) is False
    assert rbac.puede_ver_atencion(escenario["psicologo"], ficha.atencion) is True

    respuesta = _cliente(escenario["medico"]).get(f"/api/v1/psicologia/fichas/{ficha.pk}/")
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_psicologia_sigue_abriendo_procesos(escenario):
    """La corrección no puede dejar al servicio sin poder trabajar."""
    ficha = services.crear_ficha(
        expediente=escenario["expediente"],
        profesional=escenario["perfil_psico"],
        motivo="Primera entrevista",
    )
    assert ficha.atencion.servicio.codigo == "psicologia"

    respuesta = _cliente(escenario["psicologo"]).get(f"/api/v1/psicologia/fichas/{ficha.pk}/")
    assert respuesta.status_code == 200
