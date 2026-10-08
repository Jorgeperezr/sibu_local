"""
Registrar una alerta clínica desde el expediente.

`AlertaClinica` solo la creaba la carga académica masiva o el panel de
administración: no había forma de que un profesional marcara en el momento
—por ejemplo— una gestación detectada en consulta, o una enfermedad
catastrófica. La bandera es "visible en todo el expediente" por diseño del
modelo, así que no es contenido clínico narrativo y no compromete el sello.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.expediente.models import AlertaClinica
from apps.expediente.services import desactivar_alerta, registrar_alerta
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, _ = crear_profesional("medico_alerta", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()
    estudiante = Usuario.objects.create_user(
        username="estudiante_alerta", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    exp = crear_expediente(cedula="1104567894")
    return {"medico": medico, "estudiante": estudiante, "exp": exp}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_registrar_una_gestacion(escenario):
    alerta = registrar_alerta(
        escenario["exp"], AlertaClinica.Tipo.GESTACION, "Gestación de 12 semanas"
    )
    assert alerta.activa
    assert alerta.tipo == AlertaClinica.Tipo.GESTACION


@pytest.mark.django_db
def test_un_tipo_no_reconocido_se_rechaza(escenario):
    with pytest.raises(ValidationError, match="no reconocido"):
        registrar_alerta(escenario["exp"], "tipo-inventado", "algo")


@pytest.mark.django_db
def test_la_descripcion_es_obligatoria(escenario):
    with pytest.raises(ValidationError, match="descripción"):
        registrar_alerta(escenario["exp"], AlertaClinica.Tipo.NEE, "  ")


@pytest.mark.django_db
def test_registrar_la_misma_alerta_dos_veces_no_duplica(escenario):
    registrar_alerta(escenario["exp"], AlertaClinica.Tipo.LACTANCIA, "Lactancia materna exclusiva")
    registrar_alerta(escenario["exp"], AlertaClinica.Tipo.LACTANCIA, "Lactancia materna exclusiva")
    assert AlertaClinica.objects.filter(expediente=escenario["exp"]).count() == 1


@pytest.mark.django_db
def test_registrar_reactiva_una_alerta_desactivada(escenario):
    alerta = registrar_alerta(
        escenario["exp"], AlertaClinica.Tipo.ENF_CATASTROFICA, "Insuficiencia renal crónica"
    )
    desactivar_alerta(alerta)
    alerta.refresh_from_db()
    assert not alerta.activa

    registrar_alerta(
        escenario["exp"], AlertaClinica.Tipo.ENF_CATASTROFICA, "Insuficiencia renal crónica"
    )
    alerta.refresh_from_db()
    assert alerta.activa
    assert AlertaClinica.objects.filter(expediente=escenario["exp"]).count() == 1


# ------------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_registrar_desde_la_pantalla(escenario):
    cliente = _cliente(escenario["medico"])
    cliente.post(
        reverse("expediente:alertas", args=[escenario["exp"].pk]),
        {"tipo": AlertaClinica.Tipo.GESTACION, "descripcion": "Gestación de 20 semanas"},
    )
    alerta = AlertaClinica.objects.get(expediente=escenario["exp"])
    assert alerta.tipo == AlertaClinica.Tipo.GESTACION
    assert alerta.creado_por == escenario["medico"]


@pytest.mark.django_db
def test_la_alerta_aparece_en_el_detalle_del_expediente(escenario):
    registrar_alerta(
        escenario["exp"], AlertaClinica.Tipo.NEE, "Requiere tiempo adicional en exámenes"
    )
    cliente = _cliente(escenario["medico"])
    contenido = cliente.get(
        reverse("expediente:detalle", args=[escenario["exp"].pk])
    ).content.decode()
    assert "Requiere tiempo adicional en exámenes" in contenido


@pytest.mark.django_db
def test_quien_no_puede_ver_el_expediente_no_registra_alertas(escenario):
    respuesta = _cliente(escenario["estudiante"]).post(
        reverse("expediente:alertas", args=[escenario["exp"].pk]),
        {"tipo": AlertaClinica.Tipo.RIESGO, "descripcion": "x"},
    )
    assert respuesta.status_code == 403
    assert not AlertaClinica.objects.filter(expediente=escenario["exp"]).exists()
