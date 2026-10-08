"""
El POST de inicio de sesión que devolvía 403 en Codespaces.

    Forbidden (Origin checking failed - https://localhost:8000 does not match
    any trusted origins.): /cuentas/login/

La página cargaba, el formulario se veía, y al enviarlo respondía «La
verificación CSRF ha fallado». `test_csrf_dev.py` fija qué orígenes se aceptan;
esto atraviesa la vista real con ese Origin, que es lo que el usuario vio.
"""

import pytest
from django.test import Client
from django.urls import reverse

from config.settings.origenes_dev import origenes_confiables

CLAVE = "clave-larga-12345"
CODESPACE = {
    "CODESPACE_NAME": "sturdy-palm-tree-v6vxr79q67q6cxg76",
    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
}


def _intento(settings, origen: str):
    """Un inicio de sesión real con ese Origin y con CSRF activo de verdad."""
    from apps.usuarios.models import Rol, Usuario

    Usuario.objects.create_user(
        username="medico_csrf", password=CLAVE, rol_principal=Rol.PROFESIONAL
    )
    settings.CSRF_TRUSTED_ORIGINS = origenes_confiables(CODESPACE)
    # El `Client` normal no comprueba CSRF: sin `enforce_csrf_checks` esta
    # prueba pasaría siempre y no estaría comprobando nada.
    cliente = Client(enforce_csrf_checks=True)
    url = reverse("login")
    cliente.get(url, secure=True)  # deja la cookie y el token
    return cliente.post(
        url,
        {
            "csrfmiddlewaretoken": cliente.cookies["csrftoken"].value,
            "username": "medico_csrf",
            "password": CLAVE,
        },
        HTTP_ORIGIN=origen,
        secure=True,
    )


@pytest.mark.django_db
def test_el_inicio_de_sesion_ya_no_falla_con_el_origin_del_reenvio_de_puertos(settings):
    """
    La regresión completa: es el POST que respondía 403 en la pantalla del
    usuario, con el Origin que presenta el reenvío de puertos de Codespaces.
    """
    respuesta = _intento(settings, "https://localhost:8000")
    assert respuesta.status_code != 403
    assert respuesta.status_code == 302  # entró y redirige


@pytest.mark.django_db
def test_el_inicio_de_sesion_funciona_con_el_dominio_de_codespaces(settings):
    respuesta = _intento(settings, "https://sturdy-palm-tree-v6vxr79q67q6cxg76-8000.app.github.dev")
    assert respuesta.status_code == 302


@pytest.mark.django_db
def test_un_origen_ajeno_sigue_rechazandose(settings):
    """
    Ampliar la lista no puede volverla un colador: si cualquier origen pasara,
    el arreglo habría cambiado un fallo visible por uno silencioso.
    """
    assert _intento(settings, "https://atacante.example.com").status_code == 403
