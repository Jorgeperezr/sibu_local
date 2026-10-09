"""
La pantalla de bloqueo tras demasiados intentos fallidos.

django-axes trae la suya: «Account locked: too many login attempts. Please try
again later.» En inglés, fuera de la línea gráfica y sin decir cuánto hay que
esperar, sobre un sistema que está entero en español.

En una portable eso no es un detalle de traducción: **no hay administrador a
quien llamar**. Quien se equivoca cinco veces se queda mirando un error en otro
idioma sin saber que basta con esperar, y lo razonable es concluir que el
sistema se rompió.

Comprobado ejercitándolo: cinco intentos fallidos seguidos contra una portable
real devolvían ese texto en inglés.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.bloqueo import espera_legible
from apps.usuarios.models import Usuario

CLAVE = "clave-larga-12345"


# ------------------------------------------------------------ la espera legible


@pytest.mark.parametrize(
    ("horas", "esperado"),
    [
        (0.25, "15 minutos"),
        (1, "1 hora"),
        (2, "2 horas"),
        (1.5, "1 hora y 30 minutos"),
        (timedelta(minutes=20), "20 minutos"),
        (None, "unos minutos"),
    ],
)
def test_la_espera_se_dice_en_minutos_no_en_decimales(horas, esperado):
    """
    `AXES_COOLOFF_TIME` se declara en horas y admite fracciones: 0.25. Esa es
    la unidad del ajuste, no la de quien lee la pantalla.
    """
    assert espera_legible(horas) == esperado


# -------------------------------------------------------------- la pantalla


@pytest.fixture
def cuenta(db, settings):
    settings.AXES_ENABLED = True
    return Usuario.objects.create_user(username="bloqueable", password=CLAVE)


@pytest.mark.django_db
def test_tras_cinco_fallos_la_pantalla_esta_en_espanol_y_dice_cuanto(cuenta, settings):
    settings.AXES_ENABLED = True
    cliente = Client()

    respuesta = None
    for _ in range(settings.AXES_FAILURE_LIMIT + 1):
        respuesta = cliente.post(
            reverse("login"), {"username": "bloqueable", "password": "equivocada"}
        )
        if respuesta.status_code == 429:
            break

    assert respuesta.status_code == 429, "el bloqueo tiene que seguir devolviendo 429"
    contenido = respuesta.content.decode()
    assert "Acceso bloqueado temporalmente" in contenido
    assert "15 minutos" in contenido
    assert "Account locked" not in contenido, "quedó la pantalla en inglés de axes"


@pytest.mark.django_db
def test_la_pantalla_dice_que_no_se_ha_perdido_nada(cuenta, settings):
    """
    Lo que de verdad necesita saber quien la ve. Sin esto, el bloqueo se lee
    como «me borró la cuenta».
    """
    settings.AXES_ENABLED = True
    cliente = Client()
    for _ in range(settings.AXES_FAILURE_LIMIT + 1):
        respuesta = cliente.post(
            reverse("login"), {"username": "bloqueable", "password": "equivocada"}
        )
        if respuesta.status_code == 429:
            break

    contenido = respuesta.content.decode()
    assert "No ha perdido nada" in contenido
    assert "changepassword" in contenido, "en una portable no hay a quién llamar"


@pytest.mark.django_db
def test_el_bloqueo_no_devuelve_200(cuenta, settings):
    """
    El código de estado no se ablanda: un 200 haría que un cliente automático
    no distinguiera un bloqueo de un acceso correcto.
    """
    settings.AXES_ENABLED = True
    cliente = Client()
    codigos = []
    for _ in range(settings.AXES_FAILURE_LIMIT + 2):
        codigos.append(
            cliente.post(
                reverse("login"), {"username": "bloqueable", "password": "equivocada"}
            ).status_code
        )

    assert 429 in codigos
