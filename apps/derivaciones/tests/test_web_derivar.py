"""
Derivar desde la pantalla del expediente.

`derivaciones:derivar` existía desde el Sprint 5, pero ninguna pantalla
enlazaba a él: derivar exigía teclear la URL con el id de la atención a mano.
El enlace aparece solo sobre atenciones del propio servicio, que es la misma
regla que la vista aplica al entrar.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import Servicio
from apps.derivaciones import services
from apps.derivaciones.models import Derivacion
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)

CLAVE = "clave-larga-12345"


def _con_clave(usuario):
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    odonto, _ = Servicio.objects.get_or_create(
        codigo="odontologia", defaults={"nombre": "Odontología", "seccion": est["salud"]}
    )
    medico, perfil_medico = crear_profesional("medico_web", est["medicina"], est["salud"])
    odontologo, perfil_odonto = crear_profesional("odonto_web", odonto, est["salud"])
    exp = crear_expediente(cedula="1104567894")
    atencion = crear_atencion(exp, est["medicina"], perfil_medico)
    return {
        "est": est,
        "odonto": odonto,
        "medico": medico,
        "odontologo": odontologo,
        "perfil_odonto": perfil_odonto,
        "exp": exp,
        "atencion": atencion,
    }


@pytest.mark.django_db
def test_el_expediente_ofrece_derivar_desde_la_atencion_propia(escenario):
    cliente = _con_clave(escenario["medico"])
    url = reverse("expediente:detalle", args=[escenario["exp"].pk])
    contenido = cliente.get(url).content.decode()
    assert reverse("derivaciones:derivar", args=[escenario["atencion"].pk]) in contenido


@pytest.mark.django_db
def test_no_ofrece_derivar_desde_una_atencion_de_otro_servicio(escenario):
    """El odontólogo ve la atención de Medicina, pero no puede derivar desde ella."""
    cliente = _con_clave(escenario["odontologo"])
    url = reverse("expediente:detalle", args=[escenario["exp"].pk])
    contenido = cliente.get(url).content.decode()
    assert reverse("derivaciones:derivar", args=[escenario["atencion"].pk]) not in contenido
    # Y si la teclea, la vista responde 403: el enlace y el permiso van a la par.
    respuesta = cliente.get(reverse("derivaciones:derivar", args=[escenario["atencion"].pk]))
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_derivar_desde_la_pantalla_crea_la_derivacion(escenario):
    cliente = _con_clave(escenario["medico"])
    url = reverse("derivaciones:derivar", args=[escenario["atencion"].pk])
    respuesta = cliente.post(
        url,
        {
            "servicio_destino": escenario["odonto"].pk,
            "motivo": "Dolor dental persistente",
            "resumen": "Refiere molestia al masticar.",
            "prioridad": "normal",
        },
    )
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("expediente:detalle", args=[escenario["exp"].pk])
    derivacion = Derivacion.objects.get(atencion_origen=escenario["atencion"])
    assert derivacion.servicio_destino == escenario["odonto"]
    assert derivacion.estado == Derivacion.Estado.ENVIADA
    assert derivacion.creado_por == escenario["medico"]


@pytest.mark.django_db
def test_el_destino_con_derivacion_abierta_no_se_ofrece(escenario):
    services.derivar(escenario["atencion"], escenario["odonto"], motivo="Dolor dental")
    cliente = _con_clave(escenario["medico"])
    url = reverse("derivaciones:derivar", args=[escenario["atencion"].pk])
    contenido = cliente.get(url).content.decode()
    assert f'<option value="{escenario["odonto"].pk}">' not in contenido
    assert "ya tiene una derivación en curso" in contenido


@pytest.mark.django_db
def test_destinos_con_derivacion_abierta_solo_cuenta_las_vivas(escenario):
    derivacion = services.derivar(escenario["atencion"], escenario["odonto"], motivo="Dolor dental")
    assert services.destinos_con_derivacion_abierta(escenario["exp"]) == {
        escenario["odonto"].pk: escenario["odonto"].nombre
    }

    services.aceptar(derivacion)
    atencion_odonto = crear_atencion(
        escenario["exp"], escenario["odonto"], escenario["perfil_odonto"]
    )
    services.atender(derivacion, atencion_odonto)
    services.retornar(derivacion, "Se realizó profilaxis.")
    # Cerrado el ciclo, el destino vuelve a estar disponible.
    assert services.destinos_con_derivacion_abierta(escenario["exp"]) == {}


@pytest.mark.django_db
def test_el_enlace_no_abre_rendija_en_el_sello_de_psicologia(escenario):
    """
    Una atención de Psicología no se ve desde fuera, y tampoco su enlace a
    derivar: el botón se calcula sobre la lista ya filtrada por RBAC, no sobre
    todas las atenciones del expediente.
    """
    _, perfil_psicologo = crear_profesional(
        "psico_web", escenario["est"]["psicologia"], escenario["est"]["psico"]
    )
    atencion_psico = crear_atencion(
        escenario["exp"], escenario["est"]["psicologia"], perfil_psicologo
    )

    cliente = _con_clave(escenario["medico"])
    contenido = cliente.get(
        reverse("expediente:detalle", args=[escenario["exp"].pk])
    ).content.decode()
    assert reverse("derivaciones:derivar", args=[atencion_psico.pk]) not in contenido
    assert "Psicología" not in contenido
