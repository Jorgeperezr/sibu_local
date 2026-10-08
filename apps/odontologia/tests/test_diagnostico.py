"""
Diagnóstico CIE-10 desde la consulta odontológica.

`Diagnostico`/`agregar_diagnostico` viven en `apps.medicina` pero son
genéricos —la FK es a `Atencion`, no a `AtencionMedicina`—: Odontología los
reutiliza en vez de duplicar el modelo, igual que Medicina ya reutiliza
`apps.laboratorio.services` y `apps.farmacia.services`.
"""

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.core.models import CIE10, Servicio
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.medicina.models import Diagnostico
from apps.odontologia import services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    call_command("cargar_cie10")
    est = crear_estructura()
    odonto, _ = Servicio.objects.get_or_create(
        codigo="odontologia", defaults={"nombre": "Odontología", "seccion": est["salud"]}
    )
    dentista, perfil = crear_profesional("dentista_dx", odonto, est["salud"])
    dentista.set_password(CLAVE)
    dentista.save()
    exp = crear_expediente(cedula="1104567894")
    hc = services.crear_atencion_odontologia(expediente=exp, profesional=perfil, motivo="Dolor")
    return {"dentista": dentista, "hc": hc}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


@pytest.mark.django_db
def test_agregar_un_diagnostico_dental(escenario):
    cliente = _cliente(escenario["dentista"])
    cliente.post(
        reverse("odontologia:consulta", args=[escenario["hc"].pk]),
        {"accion": "diagnostico", "cie10": "K02", "tipo": "definitivo", "principal": "on"},
    )
    dx = Diagnostico.objects.get(atencion=escenario["hc"].atencion)
    assert dx.cie10 == CIE10.objects.get(codigo="K02")
    assert dx.principal


@pytest.mark.django_db
def test_el_catalogo_ofrecido_es_el_dental(escenario):
    contenido = (
        _cliente(escenario["dentista"])
        .get(reverse("odontologia:consulta", args=[escenario["hc"].pk]))
        .content.decode()
    )
    assert "K02" in contenido  # caries: dental
    assert ">F32<" not in contenido  # episodio depresivo: no es de odontología
