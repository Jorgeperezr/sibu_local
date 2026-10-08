"""
Un cero es un valor, no la ausencia de un valor.

`{% if x %}` sobre un número es falso cuando x vale 0, así que la pantalla
escondía justo los ceros que más importan:

- El **puntaje 0,00 SBU** es «extrema vulnerabilidad» —un hogar que no declara
  ingresos—. La bandeja de Trabajo Social lo pintaba como «—», indistinguible
  de una ficha sin calcular, y en la ficha el recuadro rojo del estrato no se
  dibujaba: el aviso faltaba en el único caso que lo necesita.
- Un **rango de referencia que empieza en cero** —bilirrubina directa 0 – 0,3—
  desaparecía entero de la pantalla del laboratorio.

Los dos se vieron mirando la pantalla, no en una prueba: el código de estado es
200 y el contexto llega completo; lo que falta es lo que se imprime.
"""

from decimal import Decimal

import pytest
from django.template import Context, Template


def _pinta(plantilla: str, **contexto) -> str:
    return Template("{% load textos %}" + plantilla).render(Context(contexto))


class _Ficha:
    def __init__(self, puntaje):
        self.puntaje = puntaje
        self.estrato = "Extrema vulnerabilidad"


@pytest.mark.parametrize("puntaje", [Decimal("0.00"), Decimal("0"), Decimal("1.40")])
def test_un_puntaje_calculado_siempre_se_ve(puntaje):
    salida = _pinta(
        "{% if f.puntaje is not None %}{{ f.puntaje|numero }} SBU{% else %}—{% endif %}",
        f=_Ficha(puntaje),
    )
    assert salida != "—", "un puntaje de 0 SBU es extrema vulnerabilidad, no un dato ausente"
    assert "SBU" in salida


def test_una_ficha_sin_calcular_si_dice_que_no_lo_esta():
    """Distinguir el cero de la ausencia es el objetivo; no borrar la ausencia."""
    salida = _pinta(
        "{% if f.puntaje is not None %}{{ f.puntaje|numero }} SBU{% else %}—{% endif %}",
        f=_Ficha(None),
    )
    assert salida == "—"


@pytest.mark.parametrize(
    "ref_min,ref_max,esperado",
    [
        (Decimal("0.000"), Decimal("0.300"), "0 – 0,3"),
        (Decimal("12.000"), Decimal("16.000"), "12 – 16"),
        (Decimal("4.000"), Decimal("11.000"), "4 – 11"),
    ],
)
def test_el_rango_de_referencia_se_ve_y_sin_ceros_de_relleno(ref_min, ref_max, esperado):
    """
    «12,000 – 16,000» es correcto en español —doce coma cero— pero de reojo se
    lee doce mil, y es la pantalla donde un valor mal leído tiene consecuencias.
    """

    class P:
        pass

    p = P()
    p.ref_min, p.ref_max = ref_min, ref_max
    salida = _pinta(
        "{% if p.ref_min is not None %}{{ p.ref_min|numero }} – {{ p.ref_max|numero }}"
        "{% else %}—{% endif %}",
        p=p,
    )
    assert salida == esperado


def test_el_filtro_no_convierte_el_cero_en_nada():
    """Devolver «» para el cero volvería a confundirlo con la ausencia."""
    assert _pinta("{{ v|numero }}", v=Decimal("0.000")) == "0"
    assert _pinta("{{ v|numero }}", v=None) == ""
