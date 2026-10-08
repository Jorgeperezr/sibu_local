"""
Disciplina de las plantillas: lo que evita que la interfaz se vuelva a torcer.

Estas comprobaciones existen porque los tres defectos que corrigieron nacieron
de lo mismo: reglas que se aplicaban por la POSICIÓN de un elemento en el DOM
en vez de por una clase puesta a propósito. Eso funciona hasta que alguien
mete el título dentro de un `div` o añade un `h2` antes, y entonces el fallo
aparece en una pantalla que nadie tocó.

Se leen los archivos, no se renderiza: lo que se fija es cómo están escritas
las plantillas, y eso no depende de datos ni de sesión.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
PLANTILLAS = RAIZ / "templates"

# El armazón no tiene título propio; las públicas son tarjetas centradas sin
# banda de título; la portada lleva su marca roja en `.sibu-portada` y un
# filete además sería doble.
SIN_TITULO_DE_PAGINA = {
    "base.html",
    "_nav_lista.html",
    "login.html",
    "logged_out.html",
    "inicio.html",
}


def _plantillas_de_contenido():
    """Las que dibujan una pantalla, no las parciales ni las de PDF."""
    for archivo in sorted(PLANTILLAS.rglob("*.html")):
        if archivo.name in SIN_TITULO_DE_PAGINA:
            continue
        if archivo.name.endswith("_pdf.html") or "documentos" in archivo.parts:
            continue
        if "{% block content %}" not in archivo.read_text(encoding="utf-8"):
            continue
        yield archivo


def _relativa(archivo):
    return str(archivo.relative_to(RAIZ))


def test_cada_pantalla_tiene_un_solo_titulo_de_pagina():
    """
    Uno y solo uno. Ninguno deja la pantalla sin la banda roja del manual y sin
    encabezado para un lector de pantalla; dos ponen dos bandas.
    """
    fallos = []
    for archivo in _plantillas_de_contenido():
        n = archivo.read_text(encoding="utf-8").count("sibu-titulo")
        if n != 1:
            fallos.append(f"{_relativa(archivo)} tiene {n}")
    assert not fallos, "plantillas sin exactamente un título de página: " + ", ".join(fallos)


def test_el_titulo_de_pagina_es_un_h1():
    """
    Diecinueve plantillas usaban un `<h2>` suelto como título y no tenían
    ningún `<h1>`: para un lector de pantalla la pantalla no tenía encabezado
    principal.
    """
    fallos = [
        _relativa(a)
        for a in _plantillas_de_contenido()
        if not re.search(r"<h1[^>]*\bsibu-titulo\b", a.read_text(encoding="utf-8"))
    ]
    assert not fallos, "el título de página no es un <h1>: " + ", ".join(fallos)


def test_la_hoja_de_estilos_no_estila_titulos_por_posicion():
    """
    El defecto de origen. `> h1:first-child`, `h1.h4` y `> h2:first-of-type`
    daban filete rojo al «GENERAL» de la portada —que era el primer h2— y se lo
    negaban al título de Psicología, que va dentro de un div para acompañarlo
    de una insignia.
    """
    css = (RAIZ / "static" / "css" / "sibu.css").read_text(encoding="utf-8")
    # Se examina el selector COMPLETO que precede a cada `{`, no cada línea por
    # separado: una lista de selectores repartida en varias líneas —que es
    # precisamente como estaba escrita la regla original— se le escapaba a la
    # versión anterior de esta prueba, y la falsificación lo destapó.
    sin_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    selectores = [bloque.split("}")[-1].strip() for bloque in sin_comentarios.split("{")[:-1]]
    posicionales = [
        " ".join(sel.split())
        for sel in selectores
        if ("first-child" in sel or "first-of-type" in sel or "last-child" in sel)
        and re.search(r"\bh[1-6]\b", sel)
    ]
    assert not posicionales, f"reglas de encabezado por posición: {posicionales}"


def test_ninguna_tabla_de_web_queda_sin_contenedor_de_scroll():
    """
    Una tabla sin `.table-responsive` no se encoge: cuando el contenido crece
    empuja la página entera y aparece scroll horizontal en todo el documento.
    Con el contenedor, la que se desplaza es la tabla.

    Las de PDF quedan fuera: las imprime WeasyPrint sobre papel.
    """
    fallos = []
    for archivo in sorted(PLANTILLAS.rglob("*.html")):
        if archivo.name.endswith("_pdf.html") or "documentos" in archivo.parts:
            continue
        if archivo.name == "informe_atencion.html":  # también va a papel
            continue
        texto = archivo.read_text(encoding="utf-8")
        for m in re.finditer(r"<table[^>]*>", texto):
            if "table-responsive" not in texto[max(0, m.start() - 400) : m.start()]:
                linea = texto[: m.start()].count("\n") + 1
                fallos.append(f"{_relativa(archivo)}:{linea}")
    assert not fallos, "tablas sin .table-responsive: " + ", ".join(fallos)


@pytest.mark.parametrize("clase", ["sibu-cabecera", "sibu-titulo"])
def test_las_clases_propias_estan_definidas_en_la_hoja(clase):
    """
    Una clase que las plantillas usan y el CSS no define no da error en
    ninguna parte: simplemente no hace nada, y el defecto pasa desapercibido
    hasta que alguien mira la pantalla.
    """
    css = (RAIZ / "static" / "css" / "sibu.css").read_text(encoding="utf-8")
    assert f".{clase}" in css


def test_la_cabecera_de_pagina_permite_bajar_de_linea():
    """
    El patrón `d-flex justify-content-between` SIN `flex-wrap` no baja nada de
    línea: con el título a la izquierda y una insignia a la derecha, en
    pantalla estrecha lo de la derecha se sale del viewport. Es lo que le
    pasaba a Psicología a 375 px.
    """
    css = (RAIZ / "static" / "css" / "sibu.css").read_text(encoding="utf-8")
    bloque = css.split(".sibu-cabecera {", 1)[1].split("}", 1)[0]
    assert "flex-wrap: wrap" in bloque


def test_ningun_comentario_de_plantilla_abre_sin_cerrar_en_su_linea():
    """
    `{# … #}` solo funciona en UNA línea: abierto en una y cerrado en otra,
    Django no lo trata como comentario y lo imprime en la página.

    Está anotado en la guía del proyecto y aun así volvió a pasar, escribiendo
    tres párrafos de comentario dentro de las celdas del calendario. Ninguna
    prueba lo vio porque todas miraban el contexto, no el HTML. Para varias
    líneas, `{% comment %}`.
    """
    import pathlib

    malos = []
    for archivo in pathlib.Path("templates").rglob("*.html"):
        for numero, linea in enumerate(archivo.read_text().split("\n"), 1):
            if "{#" in linea and "#}" not in linea:
                malos.append(f"{archivo}:{numero}")
    assert malos == [], (
        "comentarios {# #} repartidos en varias líneas (use {% comment %}): " + ", ".join(malos)
    )
