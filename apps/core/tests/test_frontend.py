"""
Capa visual (sprint 14).

No se prueban colores —eso es diseño, no lógica—, sino que el nuevo base.html
no rompa nada: que las páginas rendericen, que el favicon inline evite el 404, y
que los alerts se sigan pintando. Es una red de seguridad para un cambio que
toca la plantilla de la que heredan las 36.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import Seccion, Servicio
from apps.expediente.tests.factories import crear_estructura
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def admin(db):
    crear_estructura()
    becas_sec, _ = Seccion.objects.get_or_create(codigo="becas", defaults={"nombre": "Becas"})
    Servicio.objects.get_or_create(
        codigo="becas-y-ayudas-economicas",
        defaults={"nombre": "Becas", "seccion": becas_sec},
    )
    return Usuario.objects.create_user(
        username="admin", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )


@pytest.mark.django_db
def test_la_portada_renderiza_con_el_nuevo_base(admin):
    c = Client()
    c.login(username="admin", password=CLAVE)
    r = c.get(reverse("inicio"))
    assert r.status_code == 200
    cuerpo = r.content.decode()
    assert "sibu-footer" in cuerpo
    assert "css/sibu.css" in cuerpo


@pytest.mark.django_db
def test_el_favicon_evita_el_404(admin):
    """
    Antes /favicon.ico daba 404 en cada carga; luego se puso un SVG dibujado a
    mano, y ahora es el escudo de la UNL. Lo que se fija es la garantía —que
    haya un icono declarado—, no con qué se dibuja.
    """
    c = Client()
    c.login(username="admin", password=CLAVE)
    cuerpo = c.get(reverse("inicio")).content.decode()
    assert 'rel="icon"' in cuerpo
    assert "unl-escudo" in cuerpo


@pytest.mark.django_db
def test_la_pagina_de_login_usa_los_estilos(db):
    c = Client()
    cuerpo = c.get(reverse("login")).content.decode()
    assert "css/sibu.css" in cuerpo
    assert "sibu-footer" in cuerpo


@pytest.mark.django_db
def test_el_login_incorrecto_muestra_su_error(db):
    """Un flujo real que produce un alert visible con el nuevo base."""
    Usuario.objects.create_user(username="alguien", password=CLAVE)
    c = Client()
    cuerpo = c.post(reverse("login"), {"username": "alguien", "password": "mal"}).content.decode()
    assert "alert" in cuerpo


@pytest.mark.django_db
def test_modulos_que_el_admin_ve_renderizan_sin_romperse(admin):
    """
    Humo sobre módulos que heredan de base.html: cambiar la plantilla base no
    debe tumbar ninguno. Se usan los que el admin ve por rol (reportes) y las
    rutas generales (búsqueda de expedientes), no las bandejas que exigen un
    servicio asignado —su 403 es RBAC correcto, no un fallo de plantilla—.
    """
    c = Client()
    c.login(username="admin", password=CLAVE)
    for nombre in ("reportes:tablero", "expediente:buscar", "inicio"):
        r = c.get(reverse(nombre))
        assert r.status_code == 200, f"{nombre} devolvió {r.status_code}"
        assert "sibu-footer" in r.content.decode()


@pytest.mark.django_db
def test_ningun_comentario_de_plantilla_se_filtra_al_html(admin):
    """
    Un comentario {# ... #} partido en dos líneas se imprime como texto: Django
    solo los reconoce en una línea. Pasó en la portada y era visible. Esta
    prueba lo atrapa: ningún resto de sintaxis de plantilla debe llegar al HTML.
    """
    c = Client()
    c.login(username="admin", password=CLAVE)
    cuerpo = c.get(reverse("inicio")).content.decode()
    for resto in ("{#", "#}", "{% comment", "endcomment", "Mensajes centralizados"):
        assert resto not in cuerpo, f"Se filtró sintaxis de plantilla: {resto!r}"


# --------------------------------------------------------------------------
# Identidad visual de la UNL (Manual Corporativo)
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_marca_usa_el_logotipo_oficial(admin):
    """
    El manual prohíbe recomponer el logotipo: se sirve el archivo tal cual, no
    un montaje de texto e iconos. Antes la cabecera decía "SIBU · UNL" en
    tipografía suelta.
    """
    c = Client()
    c.login(username="admin", password=CLAVE)
    cuerpo = c.get(reverse("inicio")).content.decode()
    assert "img/unl-horizontal" in cuerpo


@pytest.mark.django_db
def test_los_colores_corporativos_son_los_del_manual(db):
    """
    Rojo Pantone 485 C y verde Pantone 355 C, con los valores que el manual
    declara. Antes había un verde inventado (#1b7f5a) como marcador de posición.
    """
    from pathlib import Path

    from django.conf import settings

    css = (Path(settings.BASE_DIR) / "static" / "css" / "sibu.css").read_text()
    assert "#bf0811" in css.lower()  # rojo corporativo
    assert "#4f8e3a" in css.lower()  # verde corporativo
    assert "#211915" in css.lower()  # negro corporativo
    assert "#1b7f5a" not in css.lower()  # el verde inventado ya no está


@pytest.mark.django_db
def test_la_tipografia_es_montserrat_y_se_sirve_local(db):
    """
    Montserrat es la familia principal de la marca. Se sirve desde el propio
    servidor por lo mismo que Bootstrap: un sistema interno no debe quedarse
    sin tipografía si la red bloquea Google Fonts.
    """
    from pathlib import Path

    from django.conf import settings

    css = (Path(settings.BASE_DIR) / "static" / "css" / "sibu.css").read_text()
    assert "Montserrat" in css

    cuerpo = Client().get(reverse("login")).content.decode()
    assert "vendor/montserrat/montserrat.css" in cuerpo
    assert "fonts.googleapis.com" not in cuerpo
    assert "cdn.jsdelivr.net" not in cuerpo


@pytest.mark.django_db
def test_un_mensaje_se_pinta_una_sola_vez(admin):
    """
    Cada plantilla traía su propio bloque de mensajes; al centralizarlo en
    base.html sin quitar los suyos, todo aviso salía DOS veces en pantalla.
    Se vio en una captura del alta de expediente, no en el HTML.
    """
    from django.contrib.messages import get_messages

    cliente = Client()
    cliente.login(username="admin", password=CLAVE)
    # El alta rechaza una cédula inválida con un mensaje de error.
    respuesta = cliente.post(
        reverse("expediente:nuevo"),
        {"cedula": "1104567890", "nombres": "Ana", "apellidos": "Prueba"},
        follow=True,
    )
    textos = [str(m) for m in get_messages(respuesta.wsgi_request)]
    assert textos, "la prueba necesita al menos un mensaje para contar"
    cuerpo = respuesta.content.decode()
    for texto in textos:
        assert cuerpo.count(texto) == 1, f"el mensaje se pinta {cuerpo.count(texto)} veces"


@pytest.mark.django_db
def test_un_error_se_pinta_con_el_color_de_error(admin):
    """
    Django etiqueta los errores como "error" y Bootstrap solo define
    `alert-danger`: `alert-{{ m.tags }}` producía `alert-error`, una clase
    inexistente, y el aviso salía sin color, igual que uno informativo. Se vio
    en una captura, no en el HTML.
    """
    cliente = Client()
    cliente.login(username="admin", password=CLAVE)
    respuesta = cliente.post(
        reverse("expediente:nuevo"),
        {"cedula": "1104567890", "nombres": "Ana", "apellidos": "Prueba"},
        follow=True,
    )
    cuerpo = respuesta.content.decode()
    assert "alert-danger" in cuerpo
    assert "alert-error" not in cuerpo


@pytest.mark.django_db
def test_la_marca_es_solo_el_logotipo_de_la_universidad(admin):
    """
    En la barra lateral quedó únicamente el logotipo de la UNL. El bloque con
    el nombre de la unidad se retiró por decisión del responsable del proyecto:
    apretado en 246 px no se veía bien. En los documentos PDF sí se conserva,
    donde hay ancho para componerlo como el manual pide.
    """
    cliente = Client()
    cliente.login(username="admin", password=CLAVE)
    cuerpo = cliente.get(reverse("inicio")).content.decode()
    assert "sibu-marca" in cuerpo
    assert "img/unl-horizontal.png" in cuerpo
    assert "sibu-unidad" not in cuerpo


@pytest.mark.django_db
def test_el_pie_no_lleva_la_coletilla_de_uso_interno(admin):
    cliente = Client()
    cliente.login(username="admin", password=CLAVE)
    cuerpo = cliente.get(reverse("inicio")).content.decode()
    assert "sibu-footer" in cuerpo
    assert "uso institucional" not in cuerpo
