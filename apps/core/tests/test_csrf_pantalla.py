"""
La pantalla de fallo CSRF de desarrollo.

La de Django dice «Origin checking failed - https://localhost:8000 does not
match any trusted origins» y ahí termina: no dice qué orígenes SÍ acepta ni qué
hacer. Ese mensaje costó dos rondas con un usuario que tenía el arreglo escrito
pero corría otra rama.
"""

import pytest
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.core.csrf import vista_fallo_csrf

MOTIVO = "Origin checking failed - https://localhost:8000 does not match any trusted origins."


def _pantalla(settings, origen="https://localhost:8000", confiables=None):
    settings.CSRF_TRUSTED_ORIGINS = (
        confiables if confiables is not None else ["https://sibu.unl.edu.ec"]
    )
    peticion = RequestFactory().post("/cuentas/login/", HTTP_ORIGIN=origen)
    respuesta = vista_fallo_csrf(peticion, reason=MOTIVO)
    return respuesta, respuesta.content.decode()


def test_responde_403(settings):
    respuesta, _ = _pantalla(settings)
    assert respuesta.status_code == 403


def test_dice_que_origen_llego(settings):
    """Sin esto no hay forma de saber qué está mandando el navegador."""
    _, contenido = _pantalla(settings)
    assert "https://localhost:8000" in contenido


def test_enumera_los_origenes_que_si_se_aceptan(settings):
    """
    Es la mitad que falta del mensaje de Django: saber contra qué se comparó.
    """
    _, contenido = _pantalla(settings, confiables=["https://sibu.unl.edu.ec", "http://x:8000"])
    assert "https://sibu.unl.edu.ec" in contenido
    assert "http://x:8000" in contenido


def test_avisa_cuando_el_origen_no_esta_en_la_lista(settings):
    _, contenido = _pantalla(settings, origen="https://localhost:8000")
    assert "no está en la lista de confianza" in contenido


def test_no_avisa_de_origen_ausente_cuando_si_esta(settings):
    """
    Si el Origin sí figura, el fallo es otro —un token viejo, por ejemplo— y
    señalar al origen mandaría a buscar donde no es.
    """
    _, contenido = _pantalla(
        settings, origen="https://sibu.unl.edu.ec", confiables=["https://sibu.unl.edu.ec"]
    )
    assert "no está en la lista de confianza" not in contenido


def test_dice_que_hacer(settings):
    _, contenido = _pantalla(settings)
    assert "make up" in contenido
    assert "git branch --show-current" in contenido


def test_se_dibuja_sin_sesion_ni_navegacion(settings):
    """
    No extiende `base.html` a propósito: esta pantalla debe poder dibujarse
    aunque el contexto de sesión o de navegación sea parte del problema.
    """
    _, contenido = _pantalla(settings)
    assert "<title>Verificación CSRF fallida · SIBU</title>" in contenido


def test_en_produccion_no_se_instala_esta_pantalla():
    """
    Enumera la configuración del servidor. En producción sigue el mensaje
    escueto de Django, que no la revela.

    Se lee el archivo en vez de importarlo: importar un módulo de ajustes tiene
    efectos sobre las listas que comparte con `base.py` y contaminaría el resto
    de la suite (ver `test_arranque.py`). Además `prod.py` trae dependencias que
    no hacen falta para desarrollar.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]
    prod = (raiz / "config" / "settings" / "prod.py").read_text(encoding="utf-8")
    dev = (raiz / "config" / "settings" / "dev.py").read_text(encoding="utf-8")
    assert "CSRF_FAILURE_VIEW" not in prod
    assert "CSRF_FAILURE_VIEW" in dev  # control positivo: la prueba sirve de algo


@pytest.mark.django_db
def test_el_403_real_de_un_formulario_usa_esta_pantalla(settings):
    """
    Que la vista exista no basta: tiene que ser la que Django invoca. Se
    comprueba con un POST real rechazado por origen.
    """
    settings.CSRF_FAILURE_VIEW = "apps.core.csrf.vista_fallo_csrf"
    settings.CSRF_TRUSTED_ORIGINS = ["https://sibu.unl.edu.ec"]
    cliente = Client(enforce_csrf_checks=True)
    url = reverse("login")
    cliente.get(url, secure=True)
    respuesta = cliente.post(
        url,
        {
            "csrfmiddlewaretoken": cliente.cookies["csrftoken"].value,
            "username": "x",
            "password": "y",
        },
        HTTP_ORIGIN="https://localhost:8000",
        secure=True,
    )
    assert respuesta.status_code == 403
    assert "no está en la lista de confianza" in respuesta.content.decode()
