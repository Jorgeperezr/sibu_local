"""Prueba de integración del motor de carga con un Excel sintético."""

import pandas as pd
import pytest

from apps.academico.models import CargaInstitucional, DatoAcademico
from apps.academico.services import LectorFicha, ProcesadorCarga
from apps.academico.tests.factories import generar_cedula
from apps.core.models import PeriodoAcademico
from apps.expediente.models import AlertaClinica, Persona
from apps.trabajo_social.models import FichaSocioeconomica


@pytest.fixture
def periodo(db):
    return PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril–Agosto 2026",
        fecha_inicio="2026-04-01",
        fecha_fin="2026-08-31",
        vigente=True,
    )


@pytest.fixture
def excel_ficha(tmp_path):
    ced1, ced2 = generar_cedula(11, 1111111), generar_cedula(11, 2222222)
    filas = [
        {
            "cedula": ced1,
            "nombres": "María José",
            "apellidos": "Pérez Ríos",
            "email_institucional": "mjperez@unl.edu.ec",
            "sexo": "F",
            "facultad": "Facultad de la Salud Humana",
            "carrera": "Medicina",
            "ciclo": "3",
            "modalidad": "Presencial",
            "jornada": "Matutina",
            "estado": "Matriculado",
            "paralelo": "A",
            "fecha_nacimiento": "15/03/2003",
            "ingreso_mensual": "450",
            "gastos_mensual_familia": "500",
            "violencia_familiar": "Sí",
            "estudiante_gestacion": "No",
            "viv_est_tipo": "Arrendada",
            "case": "1",
        },
        {
            "cedula": ced2,
            "nombres": "Luis",
            "apellidos": "Torres",
            "email_institucional": "ltorres@unl.edu.ec",
            "sexo": "M",
            "facultad": "Facultad de Energía",
            "carrera": "Computación",
            "ciclo": "5",
            "modalidad": "Presencial",
            "jornada": "Vespertina",
            "estado": "Matriculado",
            "paralelo": "B",
            "estudiante_necesidades_educativas_especiales": "Dislexia",
            "ingreso_mensual": "300",
        },
        {  # fila con cédula inválida -> debe contar como error
            "cedula": "0000000000",
            "nombres": "X",
            "apellidos": "Y",
        },
    ]
    ruta = tmp_path / "ficha.xlsx"
    pd.DataFrame(filas).to_excel(ruta, index=False)
    return str(ruta)


@pytest.mark.django_db
def test_carga_completa(periodo, excel_ficha):
    carga = CargaInstitucional.objects.create(
        periodo=periodo,
        nombre_archivo="ficha.xlsx",
        hash_archivo="x",
        formato="xlsx",
    )
    lector = LectorFicha(excel_ficha, "xlsx")
    resultado = ProcesadorCarga(carga).procesar(lector, aplicar=True)

    assert resultado.total == 3
    assert resultado.altas == 2
    assert resultado.errores == 1  # la cédula inválida
    assert Persona.objects.count() == 2
    assert DatoAcademico.objects.filter(periodo=periodo).count() == 2

    # Se pre-pobló la ficha socioeconómica desde matrícula
    assert (
        FichaSocioeconomica.objects.filter(origen=FichaSocioeconomica.Origen.MATRICULA).count() == 2
    )

    # Se generaron alertas (violencia familiar -> social; NEE -> nee)
    assert AlertaClinica.objects.filter(tipo="social").exists()
    assert AlertaClinica.objects.filter(tipo="nee").exists()

    # El dato académico guarda la carrera correctamente
    dato = DatoAcademico.objects.get(persona__cedula=generar_cedula(11, 1111111))
    assert dato.carrera == "Medicina"
    assert "case" in dato.ficha_raw  # la fila cruda se conserva


@pytest.mark.django_db
def test_previsualizacion_no_escribe(periodo, excel_ficha):
    carga = CargaInstitucional.objects.create(
        periodo=periodo,
        nombre_archivo="ficha.xlsx",
        hash_archivo="x",
        formato="xlsx",
    )
    lector = LectorFicha(excel_ficha, "xlsx")
    resultado = ProcesadorCarga(carga).procesar(lector, aplicar=False)
    assert resultado.altas == 2
    assert Persona.objects.count() == 0  # modo preview: no escribe


@pytest.mark.django_db
def test_reejecucion_es_idempotente(periodo, excel_ficha):
    carga = CargaInstitucional.objects.create(
        periodo=periodo,
        nombre_archivo="ficha.xlsx",
        hash_archivo="x",
        formato="xlsx",
    )
    ProcesadorCarga(carga).procesar(LectorFicha(excel_ficha, "xlsx"), aplicar=True)
    ProcesadorCarga(carga).procesar(LectorFicha(excel_ficha, "xlsx"), aplicar=True)
    assert Persona.objects.count() == 2  # no duplica
    assert DatoAcademico.objects.count() == 2
