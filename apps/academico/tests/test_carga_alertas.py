"""
Lo que la carga deja en el expediente: alertas con el tipo correcto y datos de
salud que sí llegan cuando el expediente ya existía.

El informe estadístico cuenta por TIPO de alerta. Mientras la gestación
declarada en matrícula se guardaba como "riesgo genérico", el dato estaba en la
base y no aparecía en ningún informe.
"""

import pandas as pd
import pytest

from apps.academico.models import CargaInstitucional
from apps.academico.services import LectorFicha, ProcesadorCarga
from apps.core.models import PeriodoAcademico
from apps.expediente.models import AlertaClinica, Expediente, Persona

CEDULA = "1104567894"


@pytest.fixture
def periodo(db):
    return PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril–Agosto 2026",
        fecha_inicio="2026-04-01",
        fecha_fin="2026-08-31",
        vigente=True,
    )


def _cargar(tmp_path, periodo, fila: dict):
    ruta = tmp_path / "ficha.csv"
    base = {"cedula": CEDULA, "nombres": "María José", "apellidos": "Pérez Ríos"}
    pd.DataFrame([{**base, **fila}]).to_csv(ruta, index=False)
    carga = CargaInstitucional.objects.create(
        periodo=periodo, nombre_archivo="ficha.csv", hash_archivo="x", formato="csv"
    )
    return ProcesadorCarga(carga).procesar(LectorFicha(str(ruta), "csv"), aplicar=True)


@pytest.mark.django_db
def test_la_gestacion_declarada_genera_una_alerta_de_gestacion(tmp_path, periodo):
    _cargar(tmp_path, periodo, {"estudiante_gestacion": "Sí"})
    tipos = set(AlertaClinica.objects.values_list("tipo", flat=True))
    assert AlertaClinica.Tipo.GESTACION in tipos


@pytest.mark.django_db
def test_la_lactancia_declarada_genera_una_alerta_de_lactancia(tmp_path, periodo):
    _cargar(tmp_path, periodo, {"estudiante_lactancia": "Sí"})
    tipos = set(AlertaClinica.objects.values_list("tipo", flat=True))
    assert AlertaClinica.Tipo.LACTANCIA in tipos


@pytest.mark.django_db
def test_un_no_declarado_no_genera_alerta(tmp_path, periodo):
    _cargar(tmp_path, periodo, {"estudiante_gestacion": "No", "estudiante_lactancia": "No"})
    assert not AlertaClinica.objects.exists()


@pytest.mark.django_db
def test_la_salud_de_la_ficha_llega_a_un_expediente_ya_existente(tmp_path, periodo):
    """
    `get_or_create(defaults=...)` solo aplica al crear. Si el expediente ya
    existía —lo abre también la búsqueda por cédula—, la discapacidad declarada
    en matrícula no entraba nunca, y es una de las variables del informe
    estadístico.
    """
    persona = Persona.objects.create(cedula=CEDULA, nombres="María José", apellidos="Pérez Ríos")
    expediente = Expediente.objects.create(persona=persona, numero_expediente=f"EXP-{CEDULA}")

    _cargar(
        tmp_path,
        periodo,
        {"discapacidad_tipo": "Física", "discapacidad_porcentaje": "45", "tipo_sangre": "O+"},
    )
    expediente.refresh_from_db()
    assert expediente.discapacidad_tipo == "Física"
    assert expediente.discapacidad_porcentaje == 45
    assert expediente.grupo_sanguineo == "O+"


@pytest.mark.django_db
def test_la_carga_no_pisa_lo_que_escribio_un_profesional(tmp_path, periodo):
    persona = Persona.objects.create(cedula=CEDULA, nombres="María José", apellidos="Pérez Ríos")
    Expediente.objects.create(
        persona=persona, numero_expediente=f"EXP-{CEDULA}", discapacidad_tipo="Visual"
    )
    _cargar(tmp_path, periodo, {"discapacidad_tipo": "Física"})
    assert Expediente.objects.get(persona=persona).discapacidad_tipo == "Visual"


@pytest.mark.django_db
def test_un_porcentaje_ilegible_no_tumba_la_fila(tmp_path, periodo):
    """
    La ficha llega como texto libre de un Excel. "no aplica" en un campo
    numérico no puede costar la fila entera: se descarta el dato y la fila
    cruda lo conserva igual en `ficha_raw`.
    """
    resultado = _cargar(tmp_path, periodo, {"discapacidad_porcentaje": "no aplica"})
    assert resultado.errores == 0
    assert resultado.altas == 1
    assert Expediente.objects.get(persona__cedula=CEDULA).discapacidad_porcentaje is None
