"""
Un decimal con coma es un decimal.

En Ecuador se escribe 450,50. El sistema lo leía de cuatro maneras
incompatibles —×100 al cargar, cero al sumar, vacío al guardar signos vitales,
correcto solo en Laboratorio— y ninguna avisaba. Esto fija la única lectura.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.core.numeros import a_decimal, a_decimal_o, a_entero, es_ambiguo


@pytest.mark.parametrize(
    "texto,esperado",
    [
        # Como se escribe aquí.
        ("450,50", "450.50"),
        ("0,5", "0.5"),
        ("-12,75", "-12.75"),
        # Y como lo escribe quien viene del inglés o de una hoja de cálculo.
        ("450.50", "450.50"),
        ("450", "450"),
        # Con separador de miles, en las dos convenciones: el de más a la
        # derecha es el decimal.
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("12.345.678,90", "12345678.90"),
        # Con el ruido que traen los archivos de la institución.
        ("$450,50", "450.50"),
        (" 450,50 USD", "450.50"),
    ],
)
def test_lee_el_numero_que_dice_el_texto(texto, esperado):
    from decimal import Decimal

    assert a_decimal(texto) == Decimal(esperado)


@pytest.mark.parametrize("vacio", [None, "", "   ", "$", " USD "])
def test_lo_vacio_es_none_y_no_cero(vacio):
    """
    Cero es una declaración; la ausencia de dato no lo es.

    La versión anterior devolvía `Decimal("0")` para lo vacío, así que un hogar
    que no declaró nada y uno que declaró cero quedaban idénticos.
    """
    assert a_decimal(vacio) is None


@pytest.mark.parametrize("basura", ["450,5O", "no aplica", "ninguno", "abc", "--3"])
def test_lo_que_no_es_numero_se_dice(basura):
    """Un «450,5O» con la letra O es un error de digitación, no una descripción."""
    with pytest.raises(ValidationError) as error:
        a_decimal(basura, campo="ingreso del padre")
    mensaje = " ".join(error.value.messages)
    assert basura in mensaje  # se devuelve lo recibido, para poder corregirlo
    assert "ingreso del padre" in mensaje


def test_la_version_indulgente_no_lanza():
    from decimal import Decimal

    assert a_decimal_o("no aplica", Decimal("0")) == Decimal("0")
    assert a_decimal_o("", Decimal("0")) == Decimal("0")
    assert a_decimal_o("450,50", Decimal("0")) == Decimal("450.50")


@pytest.mark.parametrize(
    "texto,ambiguo",
    [
        ("1.234", True),  # ¿mil doscientos treinta y cuatro, o uno coma 234?
        ("1,234", True),
        ("450,50", False),  # dos decimales: no hay otra lectura
        ("1.234,56", False),  # con los dos separadores no hay duda
        ("1234", False),
        ("", False),
    ],
)
def test_señala_lo_que_admite_dos_lecturas(texto, ambiguo):
    """
    Las dos lecturas de `1.234` se diferencian en MIL veces.

    No se adivina: se lee como decimal, que es la regla, y se avisa. Enterarse
    por el estrato de una familia es la otra opción.
    """
    assert es_ambiguo(texto) is ambiguo


def test_entero_con_texto_no_revienta():
    """`int("tres")` lanzaba ValueError sin capturar y salía una página de error."""
    assert a_entero("tres", 1) == 1
    assert a_entero("", 1) == 1
    assert a_entero(None, 1) == 1
    assert a_entero("4") == 4
    assert a_entero("4,0") == 4
