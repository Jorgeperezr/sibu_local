"""
El mínimo que cada endpoint de la API debe aplicar, y a quién no debe estorbar.

El barrido de `test_api_superficie.py` encontró siete puertas por las que un
estudiante leía datos que no son suyos: el padrón completo de personas y de
expedientes, las órdenes de laboratorio, las recetas, los beneficiarios de
beca, las agendas y los lotes de farmacia.

Aquí se fijan las dos caras de la corrección, porque cerrar de más habría sido
otro defecto: el farmacéutico tiene que seguir viendo las recetas y el
laboratorista sus órdenes, y ninguno de los dos tiene rol PROFESIONAL ni
servicio asignado en el sentido del RBAC clínico.
"""

import pytest
from django.core.management import call_command
from django.test import Client

from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"

# Endpoints que llevan datos de personas atendidas.
CON_PACIENTES = [
    "personas",
    "expedientes",
    "laboratorio/ordenes",
    "farmacia/recetas",
    "becas/beneficiarios",
]
# Datos internos de operación: no son de pacientes, pero tampoco públicos.
INTERNOS = ["agendas", "bloqueos-agenda", "farmacia/lotes"]


@pytest.fixture
def sembrado(db, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def _entra(username, clave):
    cliente = Client()
    assert cliente.login(username=username, password=clave), f"no entra {username}"
    return cliente


def _filas(respuesta):
    datos = respuesta.json()
    return datos["results"] if isinstance(datos, dict) and "results" in datos else datos


# ------------------------------------------------------------ lo que se cierra


@pytest.mark.django_db
@pytest.mark.parametrize("prefijo", CON_PACIENTES + INTERNOS)
def test_un_estudiante_no_lista_nada_de_esto(prefijo, sembrado):
    Usuario.objects.create_user(username="est_min", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    respuesta = _entra("est_min", CLAVE).get(f"/api/v1/{prefijo}/")
    if respuesta.status_code == 200:
        assert _filas(respuesta) == [], f"/api/v1/{prefijo}/ le devolvió filas"
    else:
        assert respuesta.status_code in (403, 404)


@pytest.mark.django_db
def test_un_estudiante_no_verifica_la_cedula_de_nadie(sembrado):
    """
    `/personas/<cedula>/verificacion/` devuelve nombre, facultad, carrera y
    estado de matrícula de quien sea. Es lo que la vista web `buscar` dejó de
    hacer y esta puerta seguía haciendo.
    """
    Usuario.objects.create_user(username="est_ver", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    respuesta = _entra("est_ver", CLAVE).get("/api/v1/personas/1100000007/verificacion/")
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_un_estudiante_no_resuelve_una_cedula_ajena_ni_le_abre_expediente(sembrado):
    """
    La peor de las tres: `PersonaViewSet.retrieve` llama a
    `resolver_por_cedula`, que no solo consulta la fuente institucional sino
    que CREA la persona y su expediente si no existían. Un estudiante abría
    expediente a quien quisiera tecleando una cédula.
    """
    from apps.expediente.models import Expediente, Persona

    Usuario.objects.create_user(username="est_ced", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    cedula = "1100000007"
    Persona.objects.filter(cedula=cedula).delete()
    antes = Expediente.objects.count()

    respuesta = _entra("est_ced", CLAVE).get(f"/api/v1/personas/{cedula}/")

    assert respuesta.status_code == 403
    assert Expediente.objects.count() == antes, "la consulta abrió un expediente"
    assert not Persona.objects.filter(cedula=cedula).exists()


# ------------------------------------------- lo que no se puede cerrar de más


@pytest.mark.django_db
def test_el_farmaceutico_sigue_viendo_las_recetas(sembrado):
    """
    Rol FARMACIA, sin rol PROFESIONAL. `rbac.atenciones_visibles` le devuelve
    cero atenciones por diseño, así que filtrar con ella habría dejado el
    mostrador vacío y roto el despacho entero.
    """
    filas = _filas(_entra("farmaceutico", "sibu-demo-2026").get("/api/v1/farmacia/recetas/"))
    assert filas, "el farmacéutico se quedó sin recetas que despachar"


@pytest.mark.django_db
def test_el_laboratorista_sigue_viendo_sus_ordenes(sembrado):
    filas = _filas(_entra("laboratorista", "sibu-demo-2026").get("/api/v1/laboratorio/ordenes/"))
    assert filas, "el laboratorista se quedó sin órdenes que procesar"


@pytest.mark.django_db
def test_quien_atiende_sigue_viendo_el_padron_de_expedientes(sembrado):
    from apps.core.management.commands.datos_demo import ADMIN

    filas = _filas(_entra(ADMIN["username"], ADMIN["clave"]).get("/api/v1/expedientes/"))
    assert filas


@pytest.mark.django_db
def test_trabajo_social_sigue_viendo_sus_beneficiarios(sembrado):
    filas = _filas(_entra("becas", "sibu-demo-2026").get("/api/v1/becas/beneficiarios/"))
    assert filas


# --------------------------------------------------------- y el sello, encima


@pytest.mark.django_db
def test_una_receta_de_psicologia_no_la_ve_farmacia(sembrado):
    """
    Psicología no receta, pero el modelo lo permite y el mostrador es de toda
    la Unidad. Si una receta saliera de allí, su existencia diría que la
    persona es paciente del servicio sellado.
    """
    from apps.core.models import Servicio
    from apps.expediente.models import Atencion, Expediente
    from apps.farmacia import services as farmacia
    from apps.farmacia.models import Medicamento
    from apps.usuarios.models import PerfilProfesional

    psico = Servicio.objects.get(codigo="psicologia")
    perfil = PerfilProfesional.objects.filter(servicios=psico).first()
    from django.utils import timezone

    atencion = Atencion.objects.create(
        expediente=Expediente.objects.first(),
        servicio=psico,
        profesional=perfil,
        fecha_hora=timezone.now(),
        motivo_consulta="Sesión",
    )
    medicamento = Medicamento.objects.first()
    receta = farmacia.emitir_receta(
        atencion,
        [{"medicamento_id": medicamento.pk, "cantidad_prescrita": 1, "indicaciones": "1 al día"}],
    )

    filas = _filas(_entra("farmaceutico", "sibu-demo-2026").get("/api/v1/farmacia/recetas/"))
    assert receta.pk not in {f["id"] for f in filas}
