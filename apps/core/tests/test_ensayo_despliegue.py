"""
El ensayo de despliegue tiene que ejercitar, no tranquilizar.

`check --deploy` mira los ajustes; el fallo que de verdad tumba un despliegue
—`CSRF_TRUSTED_ORIGINS` mal puesto— no se ve mirando: el sitio arranca, todas
las páginas responden 200 y el 403 solo aparece al enviar el primer
formulario. Por eso `ensayo_despliegue` envía uno.

De ahí lo que se comprueba aquí: que cuando entra lo dice, que cuando no entra
FALLA, y —lo que ya salió mal una vez— que cuando no lo intentó no afirme que
se puede iniciar sesión. Esa frase de más volvería inútil todo el ensayo.
"""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

pytestmark = pytest.mark.django_db

CLAVE = "Una-Clave-Larga-2026"


def _ensayar(**opciones):
    salida = StringIO()
    call_command("ensayo_despliegue", stdout=salida, stderr=salida, **opciones)
    return salida.getvalue()


@pytest.fixture
def cuenta():
    return get_user_model().objects.create_user(username="ensayo", password=CLAVE)


def test_con_credenciales_validas_el_ensayo_pasa(cuenta):
    salida = _ensayar(usuario="ensayo", clave=CLAVE)

    assert "se puede iniciar sesión" in salida


def test_sin_credenciales_no_afirma_que_se_puede_iniciar_sesion():
    salida = _ensayar()

    assert "El acceso NO se ejercitó" in salida
    assert "se puede iniciar sesión" not in salida


def test_una_clave_incorrecta_hace_fallar_el_ensayo(cuenta):
    with pytest.raises(SystemExit):
        _ensayar(usuario="ensayo", clave="otra-cosa")


def test_una_cuenta_inexistente_se_reporta_como_tal():
    salida = StringIO()
    with pytest.raises(SystemExit):
        call_command(
            "ensayo_despliegue",
            usuario="nadie",
            clave=CLAVE,
            stdout=salida,
            stderr=salida,
        )

    assert "no existe" in salida.getvalue()


def test_las_paginas_publicas_y_los_estaticos_se_reportan():
    salida = _ensayar()

    assert "/cuentas/login/" in salida
    assert "css/sibu.css" in salida


@pytest.mark.parametrize(
    ("permitidos", "esperado"),
    [
        (["*"], "testserver"),
        ([".unl.edu.ec", "sibu.unl.edu.ec"], "sibu.unl.edu.ec"),
        ([], "testserver"),
    ],
)
def test_un_comodin_de_allowed_hosts_no_sirve_para_pedir_una_pagina(permitidos, esperado):
    """`*` y `.unl.edu.ec` valen como permiso, pero no son un nombre de host."""
    from apps.core.management.commands.ensayo_despliegue import Command

    assert Command()._primer_host(permitidos) == esperado


@pytest.mark.django_db
def test_el_ensayo_recorre_los_modulos_que_la_cuenta_ve():
    """
    Lo que esta persona va a pulsar el primer día. Un 403 aquí sería una
    contradicción entre el menú y la vista, no un permiso mal puesto.
    """
    from apps.expediente.tests.factories import crear_estructura

    crear_estructura()
    get_user_model().objects.create_superuser(username="jefe", password=CLAVE)

    salida = _ensayar(usuario="jefe", clave=CLAVE)

    assert "Reportes" in salida
    assert "se puede iniciar sesión" in salida
