"""
Diagnóstico CIE-10 desde el proceso psicológico.

Complementa a `impresion_diagnostica` (texto libre): esto codifica en CIE-10
para las estadísticas del servicio, uno no reemplaza al otro. Vive en la
misma `Atencion` ya protegida por `verificar_acceso_atencion`, así que no
abre ninguna rendija en el sello.
"""

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.core.models import CIE10, Servicio
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.medicina.models import Diagnostico
from apps.psicologia import services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    call_command("cargar_cie10")
    crear_estructura()
    psico = Servicio.objects.get(codigo="psicologia")
    psicologo, perfil = crear_profesional("psicologo_dx", psico, psico.seccion)
    psicologo.set_password(CLAVE)
    psicologo.save()
    exp = crear_expediente(cedula="1104567894")
    ficha = services.crear_ficha(expediente=exp, profesional=perfil, motivo="Ansiedad")
    return {"psicologo": psicologo, "ficha": ficha, "exp": exp}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


@pytest.mark.django_db
def test_agregar_un_diagnostico_de_salud_mental(escenario):
    cliente = _cliente(escenario["psicologo"])
    cliente.post(
        reverse("psicologia:proceso", args=[escenario["ficha"].pk]),
        {"accion": "diagnostico", "cie10": "F41", "tipo": "presuntivo"},
    )
    dx = Diagnostico.objects.get(atencion=escenario["ficha"].atencion)
    assert dx.cie10 == CIE10.objects.get(codigo="F41")


@pytest.mark.django_db
def test_el_diagnostico_no_sale_del_expediente_para_quien_no_es_del_servicio(escenario):
    """El sello: el diagnóstico de Psicología sigue detrás de `verificar_acceso_atencion`."""
    from apps.core.models import Seccion
    from apps.medicina.services import agregar_diagnostico

    agregar_diagnostico(escenario["ficha"].atencion, "F41", tipo="presuntivo")

    seccion, _ = Seccion.objects.get_or_create(codigo="salud", defaults={"nombre": "Salud"})
    otro_servicio, _ = Servicio.objects.get_or_create(
        codigo="medicina", defaults={"nombre": "Medicina", "seccion": seccion}
    )
    intruso, _ = crear_profesional("intruso_dx", otro_servicio, seccion)
    intruso.set_password(CLAVE)
    intruso.save()
    respuesta = _cliente(intruso).get(reverse("psicologia:proceso", args=[escenario["ficha"].pk]))
    assert respuesta.status_code == 403
