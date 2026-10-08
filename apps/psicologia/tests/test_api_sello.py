"""
El sello de Psicología a nivel de API.

La API es una superficie NUEVA para el sello: el RBAC podría estar perfecto y
aun así un viewset mal configurado filtraría el contenido. Estas pruebas atacan
la API directamente, con usuarios reales autenticados.
"""

import pytest
from rest_framework.test import APIClient

from apps.core.models import Servicio
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.psicologia import services
from apps.psicologia.models import FichaPsicologica
from apps.usuarios.models import PerfilProfesional, Rol, Usuario


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    psico = Servicio.objects.get(codigo="psicologia")
    u_psico, psicologo = crear_profesional("psicologo", psico, psico.seccion)
    u_psico.set_password("clave12345")
    u_psico.save()
    u_med, medico = crear_profesional("medico", est["medicina"], est["salud"])
    u_med.set_password("clave12345")
    u_med.save()

    exp = crear_expediente(cedula="1104567894")
    ficha = services.crear_ficha(expediente=exp, profesional=psicologo, motivo="Ansiedad severa")
    services.registrar_sesion(
        ficha,
        profesional=psicologo,
        evolucion="Paciente refiere ideación suicida con plan estructurado.",
    )
    return {
        "est": est,
        "psico": psico,
        "psicologo": psicologo,
        "medico": medico,
        "exp": exp,
        "ficha": ficha,
        "u_psico": u_psico,
        "u_med": u_med,
    }


def _cliente(usuario):
    c = APIClient()
    c.force_authenticate(user=usuario)
    return c


def _usuario(username, rol, seccion=None):
    u = Usuario.objects.create_user(username=username, password="x", rol_principal=rol)
    if seccion is not None:
        PerfilProfesional.objects.create(usuario=u, seccion=seccion)
    return u


@pytest.mark.django_db
def test_psicologo_ve_su_ficha_por_api(escenario):
    c = _cliente(escenario["u_psico"])
    r = c.get(f"/api/v1/psicologia/fichas/{escenario['ficha'].pk}/")
    assert r.status_code == 200
    assert "ideación suicida" in str(r.json()["sesiones"])


@pytest.mark.django_db
def test_medico_no_ve_ficha_de_psicologia_por_api(escenario):
    """El detalle no se abre aunque conozca el id."""
    c = _cliente(escenario["u_med"])
    r = c.get(f"/api/v1/psicologia/fichas/{escenario['ficha'].pk}/")
    assert r.status_code in (403, 404)
    assert "ideación suicida" not in r.content.decode("utf-8")


@pytest.mark.django_db
def test_lista_de_fichas_vacia_para_ajenos(escenario):
    c = _cliente(escenario["u_med"])
    r = c.get("/api/v1/psicologia/fichas/")
    assert r.status_code == 200
    datos = r.json()
    resultados = datos["results"] if isinstance(datos, dict) else datos
    assert resultados == []


@pytest.mark.django_db
@pytest.mark.parametrize("rol", [Rol.DIRECTOR, Rol.COORDINADOR, Rol.ADMIN_GENERAL])
def test_ningun_rol_jerarquico_accede_por_api(escenario, rol):
    """Ni Dirección, ni Coordinación, ni Administración. Por API tampoco."""
    user = _usuario(f"jefe_{rol}", rol, escenario["psico"].seccion)
    c = _cliente(user)

    r = c.get(f"/api/v1/psicologia/fichas/{escenario['ficha'].pk}/")
    assert r.status_code in (403, 404), f"{rol} accedió a la ficha"
    assert "ideación suicida" not in r.content.decode("utf-8")

    r = c.get("/api/v1/psicologia/fichas/")
    resultados = r.json()["results"] if isinstance(r.json(), dict) else r.json()
    assert resultados == [], f"{rol} vio fichas en la lista"


@pytest.mark.django_db
def test_ajeno_no_puede_escribir_en_la_ficha(escenario):
    """No solo lectura: tampoco puede registrar sesiones ajenas."""
    c = _cliente(escenario["u_med"])
    r = c.post(
        f"/api/v1/psicologia/fichas/{escenario['ficha'].pk}/sesiones/",
        {"evolucion": "intruso"},
        format="json",
    )
    assert r.status_code in (403, 404)
    assert escenario["ficha"].sesiones.count() == 1


@pytest.mark.django_db
def test_catalogo_de_escalas_si_es_publico(escenario):
    """El catálogo no tiene datos de pacientes: cualquier autenticado lo lee."""
    from apps.psicologia.models import EscalaPsicometrica

    EscalaPsicometrica.objects.create(codigo="PHQ-9", nombre="PHQ-9", puntaje_max=27)
    c = _cliente(escenario["u_med"])
    r = c.get("/api/v1/psicologia/escalas/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_derivacion_a_psicologia_no_filtra_retorno_por_api(escenario):
    """
    El médico que derivó consulta la derivación por API: debe ver el acuse,
    nunca la evolución.
    """
    from apps.derivaciones import services as der_services
    from apps.expediente.tests.factories import crear_atencion

    atencion_med = crear_atencion(
        escenario["exp"], escenario["est"]["medicina"], escenario["medico"]
    )
    d = der_services.derivar(atencion_med, escenario["psico"], motivo="Evaluación")
    der_services.aceptar(d)
    atencion_psico = crear_atencion(escenario["exp"], escenario["psico"], escenario["psicologo"])
    der_services.atender(d, atencion_psico)
    der_services.retornar(d, "Ideación suicida activa, se inicia TCC urgente.")

    c = _cliente(escenario["u_med"])
    r = c.get(f"/api/v1/derivaciones/{d.pk}/")
    assert r.status_code == 200
    cuerpo = r.content.decode("utf-8")
    assert "Ideación suicida" not in cuerpo
    assert "TCC" not in cuerpo
    assert r.json()["destino_confidencial"] is True


@pytest.mark.django_db
def test_ficha_cerrada_no_admite_sesiones_por_api(escenario):
    c = _cliente(escenario["u_psico"])
    services.cerrar_proceso(escenario["ficha"], FichaPsicologica.Estado.ALTA)
    r = c.post(
        f"/api/v1/psicologia/fichas/{escenario['ficha'].pk}/sesiones/",
        {"evolucion": "otra"},
        format="json",
    )
    assert r.status_code == 400
