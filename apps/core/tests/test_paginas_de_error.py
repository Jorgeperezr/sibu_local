"""
Las tres pantallas que solo se ven cuando el sistema ya está en manos de
alguien.

Con `DEBUG=True` Django enseña su página de depuración, así que un 403, un 404
y un 500 **no se ven nunca durante el desarrollo**. En la portable —y en el
servidor— lo que salía era la página por omisión de Django: «403 Forbidden» en
inglés, en serifa, sobre blanco y sin un enlace de vuelta, en un sistema que
está entero en español.

Comprobado ejercitándolo: entrando en una portable real con una cuenta de
Administración General y abriendo `/talleres/`.

Y una trampa propia del 500: Django lo renderiza con un contexto **vacío**
—sin `request`, sin procesadores de contexto, sin `user`—. Heredar del armazón,
que arma la navegación a partir del RBAC del usuario, haría que la página de
error fallara al renderizarse, y el fallo de un error es una traza desnuda.
"""

from pathlib import Path

import pytest
from django.template.loader import get_template
from django.test import Client

from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"
PLANTILLAS = Path(__file__).resolve().parents[3] / "templates"


# ------------------------------------------------------------------- 403


@pytest.mark.django_db
def test_un_403_se_explica_en_espanol(client, settings):
    """
    Un 403 en SIBU casi nunca es un intento de colarse: es un enlace guardado
    de cuando se tenía ese servicio.
    """
    settings.DEBUG = False
    Usuario.objects.create_user(
        username="admin_403", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )
    cliente = Client(raise_request_exception=False)
    assert cliente.login(username="admin_403", password=CLAVE)

    respuesta = cliente.get("/talleres/")

    assert respuesta.status_code == 403
    contenido = respuesta.content.decode()
    assert "Forbidden" not in contenido, "quedó la página en inglés de Django"
    assert "no es de su servicio" in contenido
    assert "Administración General" in contenido, "hay que decir quién concede el acceso"
    assert 'href="/"' in contenido, "sin enlace de vuelta no hay salida"


# ------------------------------------------------------------------- 404


@pytest.mark.django_db
def test_un_404_se_explica_en_espanol(client, settings):
    settings.DEBUG = False

    respuesta = Client(raise_request_exception=False).get("/esto-no-existe/")

    assert respuesta.status_code == 404
    contenido = respuesta.content.decode()
    assert "Not Found" not in contenido
    assert "Aquí no hay nada" in contenido
    assert "No se ha perdido nada" in contenido


# ------------------------------------------------------------------- 500


def test_el_500_no_depende_del_contexto():
    """
    La trampa. Django renderiza 500.html SIN procesadores de contexto; si la
    plantilla extiende el armazón, la propia página de error revienta.
    """
    fuente = (PLANTILLAS / "500.html").read_text(encoding="utf-8")

    assert "{% extends" not in fuente, "500.html no puede heredar del armazón"
    assert "{% url" not in fuente, "`url` necesita el resolutor cargado; aquí va la ruta escrita"


def test_el_500_se_renderiza_con_el_contexto_vacio_de_django():
    """Exactamente como lo hace `django.views.defaults.server_error`."""
    salida = get_template("500.html").render({})

    assert "Algo falló" in salida
    assert "sigue guardado" in salida, "lo primero que necesita saber quien lo ve"
    assert "sibu.log" in salida, "en una portable no hay journalctl: hay que decir dónde mirar"


def test_las_tres_estan_donde_django_las_busca():
    """
    En la raíz de `templates/`, no dentro de una app: Django las carga por
    nombre y sin prefijo.
    """
    for nombre in ("403.html", "404.html", "500.html"):
        assert (PLANTILLAS / nombre).exists(), f"falta {nombre}"
        get_template(nombre)  # que además compile
