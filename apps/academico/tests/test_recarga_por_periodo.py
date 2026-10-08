"""
Qué se actualiza al volver a cargar la base en otro período, y qué no.

La base institucional se entrega cada período académico y el archivo nuevo trae
lo que cambia —ciclo, estado de matrícula, gestación—; el resto viene vacío. Con
`update_or_create` y un `defaults` completo esos huecos se escribían: **una
recarga borraba la fecha de nacimiento, el sexo, el celular y el correo** de
quien ya estaba registrado. Sin fecha de nacimiento no hay edad, sin sexo el
informe pierde una variable y sin celular no se puede llamar al paciente. Nadie
veía un error: la carga decía «1 actualización».

Tres clases de dato, y la diferencia es la regla:

- **Estable** (nombres, fecha de nacimiento, sexo…): se rellena si falta; si ya
  hay valor, no se pisa. Es el criterio que ya seguía el expediente.
- **De contacto** (celular, teléfono, correo): se actualiza cuando el archivo
  trae algo; un vacío nunca borra.
- **Del período** (ciclo, nivel, paralelo, estado): vive en `DatoAcademico`,
  una fila por período, y ahí sí cambia.
"""

import csv
import random

import pytest

from apps.academico.models import CargaInstitucional, DatoAcademico
from apps.academico.services import LectorFicha, ProcesadorCarga
from apps.academico.tests.factories import generar_cedula
from apps.core.models import PeriodoAcademico
from apps.expediente.models import AlertaClinica, Expediente, Persona


@pytest.fixture
def periodos(db):
    primero = PeriodoAcademico.objects.create(
        codigo="2026-1", nombre="Abril–Agosto", fecha_inicio="2026-04-01", fecha_fin="2026-08-31"
    )
    segundo = PeriodoAcademico.objects.create(
        codigo="2026-2", nombre="Octubre–Febrero", fecha_inicio="2026-10-01", fecha_fin="2027-02-28"
    )
    return primero, segundo


@pytest.fixture
def cedula():
    return generar_cedula(11, random.randint(1000000, 5999999))


def _cargar(tmp_path, periodo, fila):
    ruta = tmp_path / f"base-{periodo.codigo}-{random.randint(1, 999999)}.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=list(fila))
        escritor.writeheader()
        escritor.writerow(fila)
    carga = CargaInstitucional.objects.create(
        periodo=periodo, nombre_archivo=ruta.name, hash_archivo="h", formato="csv"
    )
    return ProcesadorCarga(carga).procesar(LectorFicha(str(ruta), "csv"), aplicar=True)


FICHA_COMPLETA = {
    "nombres": "Ana Lucía",
    "apellidos": "Torres Vega",
    "fecha_nacimiento": "2003-05-14",
    "sexo": "Mujer",
    "celular": "0991112233",
    "email_institucional": "ana.torres@unl.edu.ec",
    "provincia_procedencia": "Loja",
    "canton_procedencia": "Catamayo",
    "ciclo": "3",
}


@pytest.mark.django_db
def test_la_recarga_no_borra_lo_que_el_archivo_nuevo_no_trae(tmp_path, periodos, cedula):
    """El defecto que se corrige: los huecos del archivo nuevo se escribían."""
    primero, segundo = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA})

    # El archivo del período siguiente solo trae lo que cambia.
    _cargar(
        tmp_path,
        segundo,
        {"cedula": cedula, "nombres": "Ana Lucía", "apellidos": "Torres Vega", "ciclo": "4"},
    )

    persona = Persona.objects.get(cedula=cedula)
    assert str(persona.fecha_nacimiento) == "2003-05-14"
    assert persona.sexo == "Mujer"
    assert persona.celular == "0991112233"
    assert persona.correo_institucional == "ana.torres@unl.edu.ec"


@pytest.mark.django_db
def test_el_dato_del_periodo_si_cambia(tmp_path, periodos, cedula):
    """Cada período conserva el suyo: el ciclo de 2026-1 no se reescribe."""
    primero, segundo = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA})
    _cargar(
        tmp_path,
        segundo,
        {"cedula": cedula, "nombres": "Ana Lucía", "apellidos": "Torres Vega", "ciclo": "4"},
    )

    persona = Persona.objects.get(cedula=cedula)
    assert DatoAcademico.objects.get(persona=persona, periodo=primero).ciclo == "3"
    assert DatoAcademico.objects.get(persona=persona, periodo=segundo).ciclo == "4"


@pytest.mark.django_db
def test_el_contacto_se_actualiza_pero_la_identidad_no_se_pisa(tmp_path, periodos, cedula):
    """
    Un celular nuevo entra; un nombre distinto NO.

    La matrícula es la foto del día en que se llenó la ficha. Corregir un
    apellido se hace donde se corrige, no colándolo en la carga del semestre
    siguiente, que es lo mismo que ya decidió el expediente para la salud.
    """
    primero, segundo = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA})
    _cargar(
        tmp_path,
        segundo,
        {
            "cedula": cedula,
            "nombres": "OTRO NOMBRE",
            "apellidos": "OTRO APELLIDO",
            "celular": "0987654321",
        },
    )

    persona = Persona.objects.get(cedula=cedula)
    assert persona.celular == "0987654321"
    assert persona.nombres == "Ana Lucía"
    assert persona.apellidos == "Torres Vega"


@pytest.mark.django_db
def test_los_json_se_fusionan_en_vez_de_reemplazarse(tmp_path, periodos, cedula):
    """Un archivo que solo trae la provincia no puede vaciar el cantón."""
    primero, segundo = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA})
    _cargar(
        tmp_path,
        segundo,
        {
            "cedula": cedula,
            "nombres": "Ana Lucía",
            "apellidos": "Torres Vega",
            "provincia_procedencia": "Zamora",
        },
    )

    persona = Persona.objects.get(cedula=cedula)
    assert persona.procedencia["provincia_procedencia"] == "Zamora"
    assert persona.procedencia["canton_procedencia"] == "Catamayo"


@pytest.mark.django_db
def test_un_alta_nueva_entra_completa(tmp_path, periodos, cedula):
    """La cautela al actualizar no puede volverse cautela al dar de alta."""
    primero, _ = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA})

    persona = Persona.objects.get(cedula=cedula)
    assert persona.nombres == "Ana Lucía"
    assert str(persona.fecha_nacimiento) == "2003-05-14"
    assert persona.correo_institucional == "ana.torres@unl.edu.ec"


# --------------------------------------------- lo que cambia de un período a otro


@pytest.mark.django_db
def test_una_gestacion_declarada_se_apaga_cuando_el_periodo_nuevo_la_niega(
    tmp_path, periodos, cedula
):
    """
    Se encendía y no se apagaba nunca.

    `get_or_create` creaba la alerta y nada la desactivaba: un embarazo
    declarado en 2026-1 seguía activo en 2027 y el informe estadístico lo
    seguía contando como una gestación en curso.
    """
    primero, segundo = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA, "estudiante_gestacion": "Sí"})
    expediente = Expediente.objects.get(persona__cedula=cedula)
    assert expediente.alertas.filter(tipo="gestacion", activa=True).exists()

    _cargar(
        tmp_path,
        segundo,
        {
            "cedula": cedula,
            "nombres": "Ana Lucía",
            "apellidos": "Torres Vega",
            "estudiante_gestacion": "No",
        },
    )
    assert not expediente.alertas.filter(tipo="gestacion", activa=True).exists()


@pytest.mark.django_db
def test_una_columna_vacia_no_apaga_nada(tmp_path, periodos, cedula):
    """Ausencia de dato no es un «ya no»: solo apaga la negación expresa."""
    primero, segundo = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA, "estudiante_gestacion": "Sí"})
    _cargar(
        tmp_path,
        segundo,
        {"cedula": cedula, "nombres": "Ana Lucía", "apellidos": "Torres Vega", "ciclo": "4"},
    )

    expediente = Expediente.objects.get(persona__cedula=cedula)
    assert expediente.alertas.filter(tipo="gestacion", activa=True).exists()


@pytest.mark.django_db
def test_la_recarga_no_apaga_lo_que_registro_un_profesional(tmp_path, periodos, cedula):
    """
    Él lo comprobó en consulta; la ficha de matrícula no. Una recarga no es una
    segunda opinión, y por eso la alerta lleva su origen.
    """
    from apps.expediente.services import registrar_alerta

    primero, segundo = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA})
    expediente = Expediente.objects.get(persona__cedula=cedula)
    registrar_alerta(expediente, AlertaClinica.Tipo.GESTACION, "Gestación confirmada en consulta")

    _cargar(
        tmp_path,
        segundo,
        {
            "cedula": cedula,
            "nombres": "Ana Lucía",
            "apellidos": "Torres Vega",
            "estudiante_gestacion": "No",
        },
    )

    viva = expediente.alertas.get(tipo="gestacion", activa=True)
    assert viva.origen == AlertaClinica.Origen.PROFESIONAL


# ------------------------------------------------------------------- la edad


@pytest.mark.django_db
def test_la_edad_se_calcula_y_no_se_guarda(tmp_path, periodos, cedula):
    """
    Una edad almacenada envejece mal: queda congelada en la carga que la
    escribió y al año siguiente el expediente afirma una edad que ya no es
    cierta. La fecha de nacimiento no cambia nunca; la edad, cada año.
    """
    from datetime import date

    from django.utils import timezone

    primero, _ = periodos
    _cargar(tmp_path, primero, {"cedula": cedula, **FICHA_COMPLETA})
    persona = Persona.objects.get(cedula=cedula)

    hoy = timezone.localdate()
    assert persona.edad == hoy.year - 2003 - (0 if (hoy.month, hoy.day) >= (5, 14) else 1)
    assert not hasattr(Persona, "_meta") or "edad" not in [
        f.name for f in Persona._meta.get_fields()
    ], "la edad no debe ser un campo guardado"

    # Quien cumple años mañana todavía tiene la edad de ayer.
    persona.fecha_nacimiento = date(hoy.year - 20, 12, 31)
    assert persona.edad == (20 if (hoy.month, hoy.day) >= (12, 31) else 19)
