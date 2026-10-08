"""
Los montos de la ficha socioeconómica, tal como vienen en el archivo.

`a_decimal` borraba la coma antes de leer —`.replace(",", "")`—, tratándola
como separador de miles. Aquí la coma es el separador DECIMAL, así que un
ingreso declarado de «450,50» entraba a la base como **45050**: cien veces más,
en silencio, alimentando el puntaje que orienta una beca.

Y `1.234,56` entraba como 1.23456, que es mil veces menos.
"""

from decimal import Decimal

import pandas as pd
import pytest

from apps.academico.models import CargaInstitucional
from apps.academico.services import LectorFicha, ProcesadorCarga
from apps.academico.tests.factories import generar_cedula
from apps.academico.validators import a_decimal
from apps.core.models import PeriodoAcademico
from apps.trabajo_social.models import FichaSocioeconomica
from apps.trabajo_social.services import calcular_totales


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("450,50", "450.50"),  # entraba como 45050
        ("1.234,56", "1234.56"),  # entraba como 1.23456
        ("450.50", "450.50"),
        ("$450,50", "450.50"),
    ],
)
def test_el_monto_entra_por_lo_que_vale(texto, esperado):
    assert a_decimal(texto) == Decimal(esperado)


@pytest.mark.parametrize("descriptivo", ["no aplica", "ninguno", ""])
def test_una_celda_descriptiva_sigue_valiendo_cero(descriptivo):
    """Una fila no puede abortar la carga entera por traer texto en un monto."""
    assert a_decimal(descriptivo) == Decimal("0")


@pytest.fixture
def periodo(db):
    return PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril–Agosto 2026",
        fecha_inicio="2026-04-01",
        fecha_fin="2026-08-31",
        vigente=True,
    )


def _cargar(tmp_path, periodo, fila):
    ruta = tmp_path / "ficha.xlsx"
    pd.DataFrame([fila]).to_excel(ruta, index=False)
    carga = CargaInstitucional.objects.create(
        periodo=periodo, nombre_archivo="ficha.xlsx", hash_archivo="x", formato="xlsx"
    )
    resultado = ProcesadorCarga(carga).procesar(LectorFicha(str(ruta), "xlsx"), aplicar=True)
    return resultado


@pytest.mark.django_db
def test_lo_cargado_con_coma_suma_lo_mismo_que_con_punto(tmp_path, periodo):
    """
    La prueba de extremo a extremo: del archivo al puntaje.

    Es donde se veía el daño: la carga inflaba el monto y la suma de Trabajo
    Social lo descartaba, así que el mismo hogar valía 45050, 450.50 o 0 según
    por dónde se mirara.
    """
    base = {
        "cedula": generar_cedula(11, 5555555),
        "nombres": "Rosa",
        "apellidos": "Chamba",
        "ingreso_padre": "450,50",
        "ingreso_mensual": "450,50",
    }
    _cargar(tmp_path, periodo, base)

    ficha = FichaSocioeconomica.objects.get()
    assert ficha.ingresos_totales == Decimal("450.50")
    ingresos, _ = calcular_totales(ficha.ingresos, ficha.egresos)
    assert ingresos == Decimal("450.50")


@pytest.mark.django_db
def test_un_monto_ilegible_se_anota_y_no_tumba_la_fila(tmp_path, periodo):
    resultado = _cargar(
        tmp_path,
        periodo,
        {
            "cedula": generar_cedula(11, 1666666),
            "nombres": "Ana",
            "apellidos": "Ruiz",
            "ingreso_padre": "45O,50",
        },
    )
    assert resultado.errores == 0  # la fila entra
    avisos = " ".join(str(e) for e in resultado.detalle_errores)
    assert "ingreso_padre" in avisos
    assert "45O,50" in avisos


@pytest.mark.django_db
def test_un_monto_de_dos_lecturas_se_anota(tmp_path, periodo):
    """
    `1.234` puede ser mil doscientos treinta y cuatro o uno coma 234.

    No se adivina y no se rechaza: se lee según la regla y se avisa, para que
    quien carga lo vea en la bitácora en vez de enterarse por el estrato de una
    familia.
    """
    resultado = _cargar(
        tmp_path,
        periodo,
        {
            "cedula": generar_cedula(11, 2777777),
            "nombres": "Luis",
            "apellidos": "Ortega",
            "ingreso_padre": "1.234",
        },
    )
    avisos = " ".join(str(e) for e in resultado.detalle_errores)
    assert "dos lecturas" in avisos
