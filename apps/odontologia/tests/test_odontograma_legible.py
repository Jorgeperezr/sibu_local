"""
El odontograma tiene que poder LEERSE.

Dos defectos que solo se ven mirando la pantalla, no el contexto:

1. El diente sano se pintaba con `btn-success` y el obturado con
   `btn-primary`, y la línea gráfica institucional tiñe `primary` con el verde
   de la UNL: los dos salían verdes, con 1,14:1 de contraste entre sí —el mismo
   color a efectos prácticos—. Un obturado leído como sano cambia el plan de
   tratamiento y el índice CPO-D que se reporta.
2. La leyenda, escrita a mano, enseñaba seis de los diez estados. Faltaban
   «Extraído por otra causa», «Prótesis», «Implante» y «Ausente»: el
   profesional no sabía que podía registrarlos.
"""

import pathlib
import re

import pytest

from apps.odontologia import presentacion
from apps.odontologia.models import EstadoPieza

RAIZ = pathlib.Path(__file__).resolve().parents[3]
CSS = RAIZ / "static" / "css" / "sibu.css"


def test_cada_estado_tiene_su_estilo():
    """Un estado nuevo sin estilo saldría como «sin registrar», que es mentira."""
    sin_estilo = [c for c, _ in EstadoPieza.choices if c not in presentacion.ESTILOS]
    assert sin_estilo == [], f"estados sin color ni inicial: {sin_estilo}"


def test_la_leyenda_cubre_los_diez_estados():
    """Se deriva de `EstadoPieza`: escrita a mano se quedó en seis de diez."""
    assert len(presentacion.leyenda()) == len(EstadoPieza.choices)
    etiquetas = {e["etiqueta"] for e in presentacion.leyenda()}
    assert "Extraído por otra causa" in etiquetas
    assert "Ausente (no erupcionado)" in etiquetas


def test_ningun_estado_comparte_color_con_otro():
    """Dos estados del mismo color son un estado a efectos de quien mira."""
    clases = [clase for clase, _ in presentacion.ESTILOS.values()]
    assert len(clases) == len(set(clases)), f"colores repetidos: {clases}"


def test_el_odontograma_no_usa_los_colores_semanticos_de_bootstrap():
    """
    Es de donde venía el defecto: `primary` lo retiñe la línea gráfica, así que
    el obturado se volvió del mismo verde que el sano sin que nadie lo tocara.
    """
    plantilla = (RAIZ / "templates" / "odontologia" / "consulta.html").read_text()
    piezas = re.findall(r'class="odo-pieza[^"]*"', plantilla)
    assert piezas, "las piezas ya no usan la clase propia"
    for clase in piezas:
        assert "btn-primary" not in clase and "btn-success" not in clase


@pytest.mark.parametrize("estado,_etiqueta", EstadoPieza.choices)
def test_cada_color_esta_definido_en_la_hoja_de_estilos(estado, _etiqueta):
    """Una clase sin CSS deja la pieza blanca: parecería sana."""
    clase, _inicial = presentacion.estilo(estado)
    assert f".{clase}" in CSS.read_text(), f"falta .{clase} en sibu.css"


def test_el_color_no_es_lo_unico_que_distingue_un_estado():
    """
    Alrededor del 8 % de los hombres no distingue el rojo del verde, que son
    los dos estados más frecuentes, y una impresión en blanco y negro deja el
    color en nada. Cada estado registrado lleva su inicial.
    """
    sin_inicial = [
        codigo
        for codigo, (_clase, inicial) in presentacion.ESTILOS.items()
        if not inicial and codigo != EstadoPieza.SANO
    ]
    assert sin_inicial == [], f"estados que solo se distinguen por el color: {sin_inicial}"
