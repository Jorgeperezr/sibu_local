"""
La pista de credenciales en la pantalla de inicio de sesión.

Con la base ya poblada de antes, `make up` no la prepara —y hace bien: no va a
pisar datos existentes—, así que las cuentas que hay pueden no ser las de
demostración y sus contraseñas ya no se recuerdan. El aviso de arranque
menciona `make cuentas`, pero sale varias pantallas más arriba de la terminal y
para cuando hace falta ya se perdió.

La pista aparece donde uno está cuando se queda fuera: bajo el error de la
propia pantalla de inicio de sesión. Y SOLO en desarrollo: en el servidor real
decirle a cualquiera que hay cuentas de prueba sería una filtración.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.navegacion import entorno


def test_el_contexto_dice_si_esto_es_desarrollo(settings, rf):
    settings.DEBUG = True
    assert entorno(rf.get("/")) == {"es_desarrollo": True}
    settings.DEBUG = False
    assert entorno(rf.get("/")) == {"es_desarrollo": False}


def test_no_depende_de_internal_ips(settings, rf):
    """
    `django.template.context_processors.debug` solo define `debug` cuando la IP
    del cliente está en INTERNAL_IPS. En Codespaces la petición llega desde el
    reenvío de puertos y no lo está, así que aquella variable saldría vacía
    justo donde hace falta. Esta se lee de DEBUG y ya.
    """
    settings.DEBUG = True
    settings.INTERNAL_IPS = []
    peticion = rf.get("/", REMOTE_ADDR="10.1.2.3")
    assert entorno(peticion)["es_desarrollo"] is True


@pytest.mark.django_db
def test_tras_fallar_el_ingreso_la_pantalla_dice_como_ver_las_cuentas(settings):
    settings.DEBUG = True
    respuesta = Client().post(reverse("login"), {"username": "quien-sea", "password": "lo-que-sea"})
    contenido = respuesta.content.decode()
    assert "make cuentas" in contenido
    assert "make demo" in contenido


@pytest.mark.django_db
def test_en_produccion_no_se_menciona_ninguna_cuenta_de_prueba(settings):
    """
    Decirle a cualquiera que existen cuentas de prueba, y cómo listarlas, es
    una invitación a probarlas.
    """
    settings.DEBUG = False
    respuesta = Client().post(reverse("login"), {"username": "quien-sea", "password": "lo-que-sea"})
    contenido = respuesta.content.decode()
    assert "make cuentas" not in contenido
    assert "make demo" not in contenido
    # El error normal sí se sigue mostrando.
    assert "incorrectos" in contenido


@pytest.mark.django_db
def test_sin_error_no_estorba(settings):
    """La pista acompaña al fallo; no se cuela en la pantalla limpia."""
    settings.DEBUG = True
    contenido = Client().get(reverse("login")).content.decode()
    assert "make cuentas" not in contenido
