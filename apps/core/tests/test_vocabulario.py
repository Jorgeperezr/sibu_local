"""
El mismo valor escrito de varias maneras se cuenta una vez.

Cada estamento entrega su propia base y cada archivo escribe a su manera: el de
estudiantes trae «F» y «M», el de docentes «Mujer» y «Hombre». El informe
contaba «F 6, M 6, Mujer 3, Hombre 2» donde hay dos grupos, y así se entregaba
a la Dirección. Se vio en pantalla con las cuatro bases cargadas, no en una
prueba: con una sola base el defecto no existe.
"""

import pytest

from apps.core.vocabulario import normalizar


@pytest.mark.parametrize(
    "escrito,esperado",
    [
        ("F", "Mujer"),
        ("f", "Mujer"),
        ("Femenino", "Mujer"),
        ("  mujer  ", "Mujer"),
        ("M", "Hombre"),
        ("Masculino", "Hombre"),
        ("Hombre", "Hombre"),
        ("Intersexual", "Intersexual"),
    ],
)
def test_el_sexo_tiene_vocabulario_oficial_y_se_agrupa(escrito, esperado):
    assert normalizar("sexo", escrito) == esperado


@pytest.mark.parametrize(
    "escrito,esperado",
    [
        ("femenino", "Femenino"),
        ("Femenino", "Femenino"),
        ("  no binario ", "No binario"),
    ],
)
def test_el_genero_solo_se_unifica_tipograficamente(escrito, esperado):
    """
    El género y la identidad son campos LIBRES a propósito.

    Se juntan «femenino» y «Femenino», que es el mismo valor escrito distinto,
    pero no se traduce nada: meterles una tabla de sinónimos sería decidir por
    la persona cómo se nombra.
    """
    assert normalizar("genero", escrito) == esperado


def test_no_se_inventa_un_sinonimo_para_la_identidad():
    """«Lesbiana» no se convierte en nada: no hay vocabulario oficial que imponer."""
    assert normalizar("identidad_orientacion_sexual", "lesbiana") == "Lesbiana"
    assert normalizar("identidad_orientacion_sexual", "Prefiero no decirlo") == (
        "Prefiero no decirlo"
    )


def test_no_destroza_una_sigla_ni_un_valor_compuesto():
    """`capitalize()` habría convertido «VIH/SIDA» en «Vih/sida»."""
    assert normalizar("genero", "VIH/SIDA") == "VIH/SIDA"


def test_lo_vacio_se_queda_vacio():
    """Quien llama lo traduce a «Sin dato»: aquí no se inventa una categoría."""
    assert normalizar("sexo", "") == ""
    assert normalizar("sexo", None) == ""
