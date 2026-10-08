"""
Regresión: la consulta odontológica exigía solo `@login_required`.

Cualquier usuario autenticado podía abrir la historia clínica de cualquier
paciente cambiando el id en la URL. Detectado al construir la UI del Sprint 7b.
"""

import pytest
from django.test import Client

from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.odontologia import services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    from apps.core.models import Servicio

    est = crear_estructura()
    # crear_estructura() solo arma medicina y psicología: odontología se agrega aquí.
    odonto, _ = Servicio.objects.get_or_create(
        codigo="odontologia", defaults={"nombre": "Odontología", "seccion": est["salud"]}
    )
    u_dentista, dentista = crear_profesional("dentista", odonto, odonto.seccion)
    u_dentista.set_password(CLAVE)
    u_dentista.save()

    u_otro, _ = crear_profesional("otro_medico", est["medicina"], est["salud"])
    u_otro.set_password(CLAVE)
    u_otro.save()

    exp = crear_expediente(cedula="1104567894")
    hc = services.crear_atencion_odontologia(expediente=exp, profesional=dentista, motivo="Dolor")
    return {"hc": hc, "exp": exp}


@pytest.mark.django_db
def test_dentista_abre_su_consulta(escenario):
    c = Client()
    c.login(username="dentista", password=CLAVE)
    r = c.get(f"/odontologia/consulta/{escenario['hc'].pk}/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_profesional_de_otro_servicio_no_abre_la_consulta(escenario):
    """Sin RBAC en la vista, esto devolvía 200 y mostraba la historia completa."""
    c = Client()
    c.login(username="otro_medico", password=CLAVE)
    r = c.get(f"/odontologia/consulta/{escenario['hc'].pk}/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_la_bandeja_lista_las_consultas_abiertas_del_servicio(escenario):
    """La puerta de entrada del módulo: sin ella no hay enlace de menú posible."""
    c = Client()
    c.login(username="dentista", password=CLAVE)
    r = c.get("/odontologia/")
    assert r.status_code == 200
    assert "Paciente" in r.content.decode()
    assert escenario["hc"] in list(r.context["historias"])


@pytest.mark.django_db
def test_la_bandeja_niega_a_quien_no_es_del_servicio(escenario):
    """Listar los pacientes de Odontología ya es contenido del servicio."""
    c = Client()
    c.login(username="otro_medico", password=CLAVE)
    assert c.get("/odontologia/").status_code == 403
