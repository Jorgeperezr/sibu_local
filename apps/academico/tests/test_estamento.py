"""
El estamento de una carga institucional.

Hay cuatro estamentos —estudiante, docente, administrativo y trabajador— y cada
uno tiene su propia base con columnas distintas: la del estudiante trae nivel,
ciclo, paralelo y jornada, y las otras tres no. El archivo no dice a quién
describe, así que lo declara quien carga.

Antes de esto el motor escribía `TipoVinculo.ESTUDIANTE` en cada persona sin
mirar: cargar la base de docentes daba de alta al claustro entero como
estudiantes, y el informe por estamento habría contado cero docentes con las
cuatro bases cargadas.
"""

import pandas as pd
import pytest
from django.test import Client
from django.urls import reverse

from apps.academico import selectors
from apps.academico.models import CargaInstitucional
from apps.academico.services import LectorFicha, ProcesadorCarga
from apps.academico.tests.factories import generar_cedula
from apps.core.models import PeriodoAcademico
from apps.expediente.models import Persona
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


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
def archivo_docentes(tmp_path):
    """La base de docentes: sin ciclo, sin paralelo, sin jornada de clases."""
    ruta = tmp_path / "docentes.xlsx"
    pd.DataFrame(
        [
            {
                "cedula": generar_cedula(11, 3333333),
                "nombres": "Carmen",
                "apellidos": "Jaramillo",
                "facultad": "Facultad de la Salud Humana",
                "email_institucional": "cjaramillo@unl.edu.ec",
            }
        ]
    ).to_excel(ruta, index=False)
    return str(ruta)


def _carga(periodo, estamento):
    return CargaInstitucional.objects.create(
        periodo=periodo,
        estamento=estamento,
        nombre_archivo="base.xlsx",
        hash_archivo="x",
        formato="xlsx",
    )


@pytest.mark.django_db
def test_la_carga_de_docentes_da_de_alta_docentes(periodo, archivo_docentes):
    carga = _carga(periodo, Persona.TipoVinculo.DOCENTE)
    ProcesadorCarga(carga).procesar(LectorFicha(archivo_docentes, "xlsx"), aplicar=True)

    persona = Persona.objects.get(nombres="Carmen")
    assert persona.tipo_vinculo == Persona.TipoVinculo.DOCENTE


@pytest.mark.django_db
def test_por_omision_la_carga_sigue_siendo_de_estudiantes(periodo, archivo_docentes):
    """Las cargas que ya existían no cambian de sentido al añadir el campo."""
    carga = CargaInstitucional.objects.create(
        periodo=periodo, nombre_archivo="base.xlsx", hash_archivo="x", formato="xlsx"
    )
    assert carga.estamento == Persona.TipoVinculo.ESTUDIANTE
    ProcesadorCarga(carga).procesar(LectorFicha(archivo_docentes, "xlsx"), aplicar=True)
    assert Persona.objects.get(nombres="Carmen").tipo_vinculo == Persona.TipoVinculo.ESTUDIANTE


# ------------------------------------------------------------------ pantalla


def _admin(username="admin_estamento"):
    usuario = Usuario.objects.create_user(
        username=username, password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )
    cliente = Client()
    assert cliente.login(username=username, password=CLAVE)
    return usuario, cliente


@pytest.mark.django_db
def test_el_asistente_pide_el_estamento(periodo):
    _, cliente = _admin()
    contenido = cliente.get(reverse("academico:asistente")).content.decode()
    assert 'name="estamento"' in contenido
    for _valor, etiqueta in Persona.ESTAMENTOS_CHOICES:
        assert etiqueta in contenido


@pytest.mark.django_db
def test_sin_estamento_no_se_carga_nada(periodo, archivo_docentes):
    """Un archivo sin estamento declarado no puede escribir: no se sabe a quién."""
    _, cliente = _admin()
    with open(archivo_docentes, "rb") as f:
        respuesta = cliente.post(
            reverse("academico:asistente"),
            {"periodo": periodo.pk, "accion": "aplicar", "archivo": f},
        )
    assert respuesta.status_code == 200
    assert not Persona.objects.exists()
    assert not CargaInstitucional.objects.exists()


@pytest.mark.django_db
def test_un_estamento_que_no_lo_es_se_rechaza(periodo, archivo_docentes):
    """«Externo» es un vínculo válido, pero no un estamento: no hay base de externos."""
    _, cliente = _admin()
    with open(archivo_docentes, "rb") as f:
        cliente.post(
            reverse("academico:asistente"),
            {
                "periodo": periodo.pk,
                "accion": "aplicar",
                "estamento": Persona.TipoVinculo.EXTERNO,
                "archivo": f,
            },
        )
    assert not Persona.objects.exists()


@pytest.mark.django_db
def test_la_carga_por_la_pantalla_registra_el_estamento(periodo, archivo_docentes):
    _, cliente = _admin()
    with open(archivo_docentes, "rb") as f:
        cliente.post(
            reverse("academico:asistente"),
            {
                "periodo": periodo.pk,
                "accion": "aplicar",
                "estamento": Persona.TipoVinculo.ADMINISTRATIVO,
                "archivo": f,
            },
        )
    carga = CargaInstitucional.objects.get()
    assert carga.estamento == Persona.TipoVinculo.ADMINISTRATIVO
    assert Persona.objects.get(nombres="Carmen").tipo_vinculo == (
        Persona.TipoVinculo.ADMINISTRATIVO
    )


# ------------------------------------------------------- plantilla y padrón


@pytest.mark.django_db
def test_la_plantilla_de_un_no_estudiante_no_pide_columnas_de_matricula():
    columnas = selectors.columnas_ordenadas(Persona.TipoVinculo.DOCENTE)
    assert "ciclo" not in columnas
    assert "paralelo" not in columnas
    # Lo común a los cuatro estamentos sí sigue estando.
    assert "cedula" in columnas
    assert "facultad" in columnas
    assert set(columnas) < set(selectors.columnas_ordenadas())


@pytest.mark.django_db
def test_la_plantilla_se_descarga_por_estamento(periodo):
    _, cliente = _admin()
    respuesta = cliente.get(reverse("academico:plantilla"), {"estamento": "docente"})
    encabezados = respuesta.content.decode("utf-8-sig").splitlines()[0].split(",")
    assert "ciclo" not in encabezados
    assert "plantilla-base-institucional-docente.csv" in respuesta["Content-Disposition"]


@pytest.mark.django_db
def test_un_estamento_inventado_en_la_url_cae_en_estudiante(periodo):
    """Aquí el estamento solo elige columnas: no hace falta rechazar, basta no obedecer."""
    _, cliente = _admin()
    respuesta = cliente.get(reverse("academico:plantilla"), {"estamento": "rectorado"})
    encabezados = respuesta.content.decode("utf-8-sig").splitlines()[0].split(",")
    assert "ciclo" in encabezados


@pytest.mark.django_db
def test_el_padron_filtra_por_estamento():
    assert selectors.FILTROS["estamento"] == "persona__tipo_vinculo"
    assert "vinculo" not in selectors.FILTROS


@pytest.mark.django_db
def test_el_padron_ordena_por_estamento():
    """La cabecera de la columna ordena; sin esto, pulsarla no haría nada."""
    assert selectors.ORDENES["estamento"][0] == "persona__tipo_vinculo"
