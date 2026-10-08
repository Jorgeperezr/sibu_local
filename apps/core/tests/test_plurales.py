"""
Los plurales en español, y el filtro de Django que no sirve para ellos.

`pluralize` pega una terminación al final de la palabra tal como está escrita.
En español eso falla cada vez que el singular lleva tilde en la última sílaba:
para escribir «atenciones» hay que poner `atencion{{ n|pluralize:"es" }}`, y
entonces el singular sale «1 atencion», sin tilde.

No es hipotético ni menor: se veía en la pantalla del informe y en el PDF que
se entrega, después de que el mismo problema ya se hubiera resuelto a mano dos
veces en otros sitios. Lo que se ve aquí es lo que se firma.
"""

import pathlib
import re

import pytest
from django.template import Context, Template

RAIZ = pathlib.Path(__file__).resolve().parents[3]

# Palabras cuyo plural NO se forma pegando letras al singular escrito.
# Son las que llevan tilde en la última sílaba: al pluralizar, la pierden.
ACENTUADAS_EN_LA_ULTIMA = (
    "atencion",
    "derivacion",
    "notificacion",
    "sesion",
    "version",
    "aplicacion",
    "prescripcion",
    "autorizacion",
)


def _plantillas():
    return sorted(RAIZ.glob("templates/**/*.html"))


def test_hay_plantillas_que_revisar():
    """Si la ruta cambia y esto queda vacío, la prueba de abajo pasaría sola."""
    assert len(_plantillas()) >= 30


@pytest.mark.parametrize("plantilla", _plantillas(), ids=lambda p: p.name)
def test_ninguna_plantilla_pluraliza_una_palabra_acentuada(plantilla):
    """
    `pluralize` sobre «atencion» imprime «1 atencion». Use el filtro `plural`,
    que pide las dos formas: `{{ n|plural:"atención,atenciones" }}`.
    """
    texto = plantilla.read_text()
    culpables = []
    for palabra in ACENTUADAS_EN_LA_ULTIMA:
        # La palabra, sin tilde, pegada a un `pluralize`.
        if re.search(rf"{palabra}\s*\{{\{{[^}}]*\|\s*pluralize", texto):
            culpables.append(palabra)
    assert culpables == [], (
        f"{plantilla.name} pluraliza {culpables} con `pluralize`: el singular "
        'saldría sin tilde. Use `{{ n|plural:"atención,atenciones" }}`.'
    )


@pytest.mark.parametrize(
    "cantidad,esperado",
    [(1, "atención"), (0, "atenciones"), (2, "atenciones"), (None, "atenciones")],
)
def test_el_filtro_da_la_forma_correcta(cantidad, esperado):
    """Cero va en plural: en español se dice «0 atenciones»."""
    plantilla = Template('{% load textos %}{{ n|plural:"atención,atenciones" }}')
    assert plantilla.render(Context({"n": cantidad})) == esperado
