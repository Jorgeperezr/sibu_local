"""
El sello de Psicología en la interfaz web.

Las vistas de plantilla no pasan por los permisos de DRF: necesitan su propia
comprobación. `@login_required` por sí solo dejaría abrir la ficha de cualquier
paciente cambiando el id en la URL.
"""

import pytest
from django.test import Client

from apps.core.models import Servicio
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.psicologia import services
from apps.usuarios.models import PerfilProfesional, Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    psico = Servicio.objects.get(codigo="psicologia")
    u_psico, psicologo = crear_profesional("psicologo", psico, psico.seccion)
    u_psico.set_password(CLAVE)
    u_psico.save()
    u_med, medico = crear_profesional("medico", est["medicina"], est["salud"])
    u_med.set_password(CLAVE)
    u_med.save()

    exp = crear_expediente(cedula="1104567894")
    ficha = services.crear_ficha(expediente=exp, profesional=psicologo, motivo="Ansiedad")
    services.registrar_sesion(
        ficha, profesional=psicologo, evolucion="Refiere ideación suicida con plan."
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


def _login(username):
    c = Client()
    assert c.login(username=username, password=CLAVE)
    return c


@pytest.mark.django_db
def test_psicologo_abre_el_proceso(escenario):
    c = _login("psicologo")
    r = c.get(f"/psicologia/proceso/{escenario['ficha'].pk}/")
    assert r.status_code == 200
    assert "ideación suicida" in r.content.decode("utf-8")


@pytest.mark.django_db
def test_medico_no_abre_el_proceso_por_url(escenario):
    """Cambiar el id en la URL no basta: 403."""
    c = _login("medico")
    r = c.get(f"/psicologia/proceso/{escenario['ficha'].pk}/")
    assert r.status_code == 403
    assert "ideación suicida" not in r.content.decode("utf-8")


@pytest.mark.django_db
def test_medico_no_entra_a_la_bandeja_de_psicologia(escenario):
    c = _login("medico")
    r = c.get("/psicologia/")
    assert r.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("rol", [Rol.DIRECTOR, Rol.COORDINADOR, Rol.ADMIN_GENERAL])
def test_roles_jerarquicos_no_abren_el_proceso(escenario, rol):
    u = Usuario.objects.create_user(username=f"jefe{rol}", password=CLAVE, rol_principal=rol)
    PerfilProfesional.objects.create(usuario=u, seccion=escenario["psico"].seccion)
    c = _login(f"jefe{rol}")
    r = c.get(f"/psicologia/proceso/{escenario['ficha'].pk}/")
    assert r.status_code == 403, f"{rol} abrió el proceso"
    assert "ideación suicida" not in r.content.decode("utf-8")


@pytest.mark.django_db
def test_medico_no_registra_sesiones_ajenas(escenario):
    c = _login("medico")
    r = c.post(
        f"/psicologia/proceso/{escenario['ficha'].pk}/",
        {"accion": "sesion", "evolucion": "intruso"},
    )
    assert r.status_code == 403
    assert escenario["ficha"].sesiones.count() == 1


@pytest.mark.django_db
def test_bandeja_muestra_procesos_al_psicologo(escenario):
    c = _login("psicologo")
    r = c.get("/psicologia/")
    assert r.status_code == 200
    assert escenario["exp"].persona.nombre_completo in r.content.decode("utf-8")
