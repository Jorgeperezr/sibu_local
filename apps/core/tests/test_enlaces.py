"""
Lo que la interfaz enlaza tiene que poder abrirse.

Cerrar sesión era `<a href="{% url 'logout' %}">` y Django 5 retiró el GET de
`LogoutView`: quien pulsaba el icono recibía un **405 Method Not Allowed**. La
pantalla respondía, el enlace existía, la URL era correcta y el barrido de
acceso pasaba: nadie comprobaba que un enlace se pudiera SEGUIR.

Un `<a href>` es una petición GET. Enlazar así una vista que solo acepta POST
es un fallo de la plantilla, no de la vista: las de POST —cerrar sesión, marcar
leída una notificación— existen por una razón. Con un GET, un tercero cierra
la sesión ajena metiendo un `<img src="/cuentas/logout/">` en cualquier página.
Lo que hay que corregir es el enlace, no el método.

Este barrido recorre las plantillas, saca los `{% url %}` que viven dentro de
un `href` y comprueba que respondan a GET. Un enlace nuevo entra solo.
"""

import pathlib
import re

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import NoReverseMatch, reverse

RAIZ = pathlib.Path(__file__).resolve().parents[3]

# `href="{% url 'nombre' ... %}"`, con comilla simple o doble alrededor del
# nombre. Se admite lo que venga después —argumentos, un `?param=`— porque solo
# interesa a qué apunta.
ENLACE = re.compile(r"""href=["']\{%\s*url\s+['"]([\w:.-]+)['"]([^%]*)%\}""")

# Cuentas de la siembra que dan acceso a lo que enlaza cada plantilla. Se prueba
# con la de administración: es la que llega a más pantallas sin ser un rol
# clínico. Lo que no alcance responderá 403, que también sirve —el barrido
# busca el 405, no el permiso—.
ADMIN = ("1104346091", "1104346091")


def _plantillas():
    return sorted(RAIZ.glob("templates/**/*.html"))


def _enlaces_de(plantilla: pathlib.Path) -> set[tuple[str, bool]]:
    """{(nombre de la url, si lleva argumentos)} de los `href` de la plantilla."""
    encontrados = set()
    for nombre, resto in ENLACE.findall(plantilla.read_text()):
        encontrados.add((nombre, bool(resto.strip())))
    return encontrados


def _todos_los_enlaces() -> list[tuple[str, bool, str]]:
    return sorted(
        {
            (nombre, con_args, plantilla.name)
            for plantilla in _plantillas()
            for nombre, con_args in _enlaces_de(plantilla)
        }
    )


@pytest.fixture
def sembrado(db, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def test_el_barrido_encuentra_enlaces():
    """Si la expresión deja de coincidir, la prueba de abajo pasaría sola."""
    assert len(_todos_los_enlaces()) >= 20


@pytest.mark.django_db
def test_ningun_enlace_apunta_a_una_vista_que_rechaza_el_get(sembrado):
    """
    Un `<a href>` es un GET. Si la vista solo acepta POST, el usuario ve un 405.

    Es lo que pasaba con cerrar sesión. El arreglo va en la plantilla —un
    formulario POST con su CSRF—, nunca en la vista.
    """
    cliente = Client()
    assert cliente.login(username=ADMIN[0], password=ADMIN[1]), "no entra la cuenta de prueba"

    rotos = []
    for nombre, con_args, plantilla in _todos_los_enlaces():
        try:
            url = reverse(nombre, args=[1]) if con_args else reverse(nombre)
        except NoReverseMatch:
            # Un enlace con argumentos que no encajan con un `1` no se puede
            # construir aquí; no es lo que este barrido juzga.
            continue
        try:
            respuesta = cliente.get(url)
        except Exception:
            continue  # una vista que revienta con un id inventado es otra cosa
        if respuesta.status_code == 405:
            rotos.append(f"{plantilla}: href a «{nombre}» ({url}) devuelve 405")
    assert rotos == [], (
        "enlaces que el usuario no puede seguir; use un formulario POST en la "
        "plantilla, no cambie el método de la vista: " + "; ".join(rotos)
    )


@pytest.mark.django_db
def test_cerrar_sesion_va_por_post_y_funciona(sembrado):
    """
    El caso concreto que se rompió, con su porqué.

    Django 5 retiró el GET de `LogoutView` justamente para que un tercero no
    pueda cerrar la sesión ajena con un `<img src="/cuentas/logout/">`.
    """
    cliente = Client()
    assert cliente.login(username=ADMIN[0], password=ADMIN[1])

    assert (
        cliente.get(reverse("logout")).status_code == 405
    ), "la vista debe seguir rechazando el GET: es lo que protege la sesión"
    respuesta = cliente.post(reverse("logout"))
    assert respuesta.status_code in (200, 302)
    assert "_auth_user_id" not in cliente.session, "la sesión no se cerró"


@pytest.mark.django_db
def test_la_plantilla_base_cierra_sesion_con_un_formulario(sembrado):
    """Lo que se pinta, no lo que se puede pintar: aquí estaba el `<a href>`."""
    cliente = Client()
    assert cliente.login(username=ADMIN[0], password=ADMIN[1])
    contenido = cliente.get("/").content.decode()

    assert 'action="/cuentas/logout/"' in contenido, "no hay formulario de cierre de sesión"
    assert 'href="/cuentas/logout/"' not in contenido, "quedó un enlace de cierre de sesión"
