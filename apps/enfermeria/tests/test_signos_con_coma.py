"""
Un signo vital no se pierde en silencio.

`_dec` devolvía `None` tanto para lo vacío como para lo ilegible, así que una
temperatura escrita «36,5» —como se escribe un decimal aquí— se guardaba VACÍA
y la pantalla contestaba «Signos vitales registrados». El triaje quedaba
incompleto y nadie tenía motivo para revisarlo: no hubo error.

Dos reglas: la coma se lee, y lo que no sea un número se dice y no se guarda
nada. Guardar el resto y callar el dato ilegible dejaría un triaje a medias
que parecería completo.
"""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import Servicio
from apps.enfermeria.models import SignosVitales
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    enfermeria, _ = Servicio.objects.get_or_create(
        codigo="enfermeria", defaults={"nombre": "Enfermería", "seccion": est["salud"]}
    )
    enfermera, _perfil = crear_profesional("enf_coma", enfermeria, est["salud"])
    enfermera.set_password(CLAVE)
    enfermera.save()
    cliente = Client()
    assert cliente.login(username="enf_coma", password=CLAVE)
    return {"cliente": cliente, "expediente": crear_expediente(cedula="1104567894")}


@pytest.mark.django_db
def test_la_temperatura_con_coma_se_guarda(escenario):
    escenario["cliente"].post(
        reverse("enfermeria:triaje", args=[escenario["expediente"].pk]),
        {"temperatura": "36,5", "peso": "58,4", "fc": "72"},
    )
    signos = SignosVitales.objects.get()
    assert signos.temperatura == Decimal("36.5")
    assert signos.peso == Decimal("58.4")
    assert signos.fc == 72


@pytest.mark.django_db
def test_un_valor_ilegible_avisa_y_no_guarda_un_triaje_a_medias(escenario):
    respuesta = escenario["cliente"].post(
        reverse("enfermeria:triaje", args=[escenario["expediente"].pk]),
        {"temperatura": "treinta y seis", "fc": "72"},
        follow=True,
    )
    contenido = respuesta.content.decode()
    assert "temperatura" in contenido
    # Ni el dato ilegible ni los que venían con él: un triaje incompleto que
    # nadie sabe que lo está es peor que uno que no se guardó.
    assert not SignosVitales.objects.exists()


@pytest.mark.django_db
def test_los_campos_vacios_siguen_siendo_opcionales(escenario):
    """No todo triaje toma todos los signos: lo vacío no es un error."""
    escenario["cliente"].post(
        reverse("enfermeria:triaje", args=[escenario["expediente"].pk]),
        {"temperatura": "36.5", "peso": "", "fc": ""},
    )
    signos = SignosVitales.objects.get()
    assert signos.peso is None
    assert signos.fc is None
