"""
El inicio de sesión.

La ruta django.contrib.auth.urls estaba enrutada desde el principio, pero sin
la plantilla registration/login.html: /cuentas/login/ devolvía 500. El sistema
no tenía pantalla de acceso; solo no se notaba porque se entraba por /admin/.
Estas pruebas fijan que la puerta de entrada funcione.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.mark.django_db
def test_la_pagina_de_login_carga(db):
    """Antes daba 500 por plantilla ausente. Debe renderizar."""
    c = Client()
    r = c.get(reverse("login"))
    assert r.status_code == 200
    assert "Ingresar" in r.content.decode()


@pytest.mark.django_db
def test_login_correcto_entra_y_redirige(db):
    Usuario.objects.create_user(
        username="jorgeperez", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )
    c = Client()
    r = c.post(reverse("login"), {"username": "jorgeperez", "password": CLAVE})
    assert r.status_code == 302
    # LOGIN_REDIRECT_URL = inicio
    assert r.url == reverse("inicio")


@pytest.mark.django_db
def test_login_incorrecto_no_entra(db):
    Usuario.objects.create_user(username="jorgeperez", password=CLAVE)
    c = Client()
    r = c.post(reverse("login"), {"username": "jorgeperez", "password": "equivocada"})
    assert r.status_code == 200  # vuelve al formulario
    assert not r.wsgi_request.user.is_authenticated


@pytest.mark.django_db
def test_logout_cierra_la_sesion(db):
    """
    LOGOUT_REDIRECT_URL='login' redirige tras salir en vez de mostrar la
    página de despedida. La plantilla logged_out queda como respaldo si esa
    configuración cambia; lo que importa aquí es que la sesión se cierre.
    """
    Usuario.objects.create_user(username="jorgeperez", password=CLAVE)
    c = Client()
    c.login(username="jorgeperez", password=CLAVE)
    r = c.post(reverse("logout"))
    assert r.status_code == 302
    assert reverse("login") in r.url
    # La sesión quedó cerrada: una vista protegida ya no entra.
    assert c.get("/reportes/").status_code == 302


@pytest.mark.django_db
def test_una_vista_protegida_redirige_al_login(db):
    """El flujo completo: sin sesión, una vista con login_required manda al login."""
    c = Client()
    r = c.get("/reportes/")
    assert r.status_code == 302
    assert reverse("login") in r.url
