"""
Regresión: el escritorio de consulta médica exigía solo `@login_required`.

Mismo bug que el Sprint 7b corrigió en Odontología y Psicología, pero que en
Medicina quedó sin corregir: cualquier usuario autenticado —incluido un
estudiante del portal— abría la historia clínica completa de cualquier
paciente cambiando el id de la URL.
"""

import pytest
from django.test import Client

from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.medicina import services
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    from apps.core.models import Servicio

    est = crear_estructura()
    medicina = est["medicina"]
    u_medico, medico = crear_profesional("medico", medicina, est["salud"])
    u_medico.set_password(CLAVE)
    u_medico.save()

    # Un profesional de otro servicio de la misma sección.
    farmacia, _ = Servicio.objects.get_or_create(
        codigo="farmacia", defaults={"nombre": "Farmacia", "seccion": est["salud"]}
    )
    u_otro, _ = crear_profesional("farmaceutico", farmacia, est["salud"])
    u_otro.set_password(CLAVE)
    u_otro.save()

    exp = crear_expediente(cedula="1100000007")
    hc = services.crear_atencion_medicina(expediente=exp, profesional=medico, motivo="Cefalea")
    return {"hc": hc, "exp": exp, "medicina": medicina, "salud": est["salud"]}


@pytest.mark.django_db
def test_el_medico_abre_su_consulta(escenario):
    c = Client()
    c.login(username="medico", password=CLAVE)
    assert c.get(f"/medicina/consulta/{escenario['hc'].pk}/").status_code == 200


@pytest.mark.django_db
def test_profesional_de_otro_servicio_no_abre_la_consulta(escenario):
    """Sin RBAC en la vista esto devolvía 200 y mostraba la historia completa."""
    c = Client()
    c.login(username="farmaceutico", password=CLAVE)
    assert c.get(f"/medicina/consulta/{escenario['hc'].pk}/").status_code == 403


@pytest.mark.django_db
def test_un_estudiante_del_portal_no_abre_la_consulta(escenario):
    """El caso más grave: un usuario final leyendo historias clínicas ajenas."""
    Usuario.objects.create_user(
        username="estudiante", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    c = Client()
    c.login(username="estudiante", password=CLAVE)
    assert c.get(f"/medicina/consulta/{escenario['hc'].pk}/").status_code == 403


@pytest.mark.django_db
def test_la_bandeja_lista_las_consultas_abiertas_del_servicio(escenario):
    c = Client()
    c.login(username="medico", password=CLAVE)
    r = c.get("/medicina/")
    assert r.status_code == 200
    assert escenario["hc"] in list(r.context["historias"])


@pytest.mark.django_db
def test_la_bandeja_niega_a_quien_no_es_del_servicio(escenario):
    c = Client()
    c.login(username="farmaceutico", password=CLAVE)
    assert c.get("/medicina/").status_code == 403
