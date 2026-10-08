"""
Regresión: el triaje exigía solo `@login_required`.

Los signos vitales son contenido clínico del expediente. Sin comprobación de
servicio, cualquier autenticado los leía —y los registraba— sobre el
expediente de cualquiera cambiando el id de la URL.
"""

import pytest
from django.test import Client

from apps.enfermeria.models import SignosVitales
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    from apps.core.models import Servicio

    est = crear_estructura()
    # crear_estructura() arma medicina y psicología: enfermería se agrega aquí.
    enfermeria, _ = Servicio.objects.get_or_create(
        codigo="enfermeria", defaults={"nombre": "Enfermería", "seccion": est["salud"]}
    )
    u_enfermera, enfermera = crear_profesional("enfermera_ui", enfermeria, est["salud"])
    u_enfermera.set_password(CLAVE)
    u_enfermera.save()

    u_otro, _ = crear_profesional("medico_ui", est["medicina"], est["salud"])
    u_otro.set_password(CLAVE)
    u_otro.save()

    exp = crear_expediente(cedula="1100000007")
    return {"exp": exp, "enfermeria": enfermeria, "enfermera": enfermera}


@pytest.mark.django_db
def test_la_enfermera_abre_el_triaje(escenario):
    c = Client()
    c.login(username="enfermera_ui", password=CLAVE)
    assert c.get(f"/enfermeria/triaje/{escenario['exp'].pk}/").status_code == 200


@pytest.mark.django_db
def test_profesional_de_otro_servicio_no_abre_el_triaje(escenario):
    """Sin RBAC esto devolvía 200 con los signos vitales del paciente."""
    c = Client()
    c.login(username="medico_ui", password=CLAVE)
    assert c.get(f"/enfermeria/triaje/{escenario['exp'].pk}/").status_code == 403


@pytest.mark.django_db
def test_un_estudiante_del_portal_no_registra_signos(escenario):
    """El POST también estaba abierto: se podían inventar signos ajenos."""
    Usuario.objects.create_user(
        username="estudiante_enf", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    c = Client()
    c.login(username="estudiante_enf", password=CLAVE)
    r = c.post(f"/enfermeria/triaje/{escenario['exp'].pk}/", {"temperatura": "38.5"})
    assert r.status_code == 403
    assert not SignosVitales.objects.filter(expediente=escenario["exp"]).exists()


@pytest.mark.django_db
def test_la_bandeja_lista_los_triajes_del_dia(escenario):
    SignosVitales.objects.create(
        expediente=escenario["exp"], temperatura="37.0", responsable=escenario["enfermera"]
    )
    c = Client()
    c.login(username="enfermera_ui", password=CLAVE)
    r = c.get("/enfermeria/")
    assert r.status_code == 200
    assert len(r.context["triajes"]) == 1


@pytest.mark.django_db
def test_la_bandeja_niega_a_quien_no_es_del_servicio(escenario):
    c = Client()
    c.login(username="medico_ui", password=CLAVE)
    assert c.get("/enfermeria/").status_code == 403
