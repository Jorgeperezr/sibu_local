"""
La trazabilidad no puede ser la puerta trasera del sello de Psicología.

`trazabilidad` devuelve el recorrido del paciente entre servicios: de dónde
salió, a dónde fue y con qué motivo. Sobre un destino confidencial eso es dos
filtraciones a la vez:

- El **motivo** lo escribe quien deriva y suele decir por qué: es contenido.
- La **existencia misma** de la fila «→ Psicología» identifica a la persona
  como paciente de Psicología, aunque el motivo estuviera en blanco.

Y ni la vista web ni el endpoint comprobaban nada: bastaba con estar
autenticado y cambiar el id del expediente en la URL. Es exactamente la
regresión que el Sprint 7b corrigió en nueve vistas y que aquí quedó viva.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.derivaciones import services
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"
MOTIVO_SENSIBLE = "Ideación suicida referida por la docente"


@pytest.fixture
def escenario(db):
    """Medicina deriva a Psicología. El motivo dice por qué, como en la vida real."""
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("med_traza", est["medicina"], est["salud"])
    psicologo, _ = crear_profesional("psi_traza", est["psicologia"], est["psico"])
    expediente = crear_expediente()
    atencion = crear_atencion(expediente, est["medicina"], perfil_medico)
    derivacion = services.derivar(
        atencion,
        est["psicologia"],
        motivo=MOTIVO_SENSIBLE,
        usuario=medico,
    )
    return {
        "est": est,
        "medico": medico,
        "psicologo": psicologo,
        "expediente": expediente,
        "atencion": atencion,
        "derivacion": derivacion,
    }


def _cliente(usuario):
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


def _ajeno(username="ajeno", rol=Rol.USUARIO_FINAL):
    return Usuario.objects.create_user(username=username, password=CLAVE, rol_principal=rol)


# ------------------------------------------------------- quién puede mirar


@pytest.mark.django_db
def test_un_estudiante_no_abre_la_trazabilidad_de_nadie(escenario):
    """
    El caso que estaba abierto: `@login_required` a secas. Un estudiante con
    rol USUARIO_FINAL cambiaba el id del expediente y leía el recorrido.
    """
    cliente = _cliente(_ajeno())
    respuesta = cliente.get(reverse("derivaciones:trazabilidad", args=[escenario["expediente"].pk]))
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_el_endpoint_tampoco_lo_deja(escenario):
    """La API es otra puerta a lo mismo, y estaba igual de abierta."""
    cliente = _cliente(_ajeno("ajeno_api"))
    respuesta = cliente.get(
        "/api/v1/derivaciones/trazabilidad/", {"expediente": escenario["expediente"].pk}
    )
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_quien_atiende_sí_la_abre(escenario):
    """La corrección no puede cerrarle la puerta a quien la necesita."""
    cliente = _cliente(escenario["medico"])
    respuesta = cliente.get(reverse("derivaciones:trazabilidad", args=[escenario["expediente"].pk]))
    assert respuesta.status_code == 200


# ------------------------------------------- qué se ve de un destino sellado


@pytest.mark.django_db
def test_un_servicio_ajeno_no_ve_ni_que_existe_la_derivacion_a_psicologia(escenario):
    """
    Lo más fino del sello: no basta con tapar el motivo. Que aparezca la fila
    «→ Psicología» ya dice que esta persona es paciente de Psicología, y eso
    es justo lo que no puede salir del servicio.
    """
    est = escenario["est"]
    enfermera, _ = crear_profesional("enf_traza", est["medicina"], est["salud"])
    # Un servicio distinto del origen y del destino.
    from apps.core.models import Servicio

    odonto = Servicio.objects.create(
        codigo="odontologia", nombre="Odontología", seccion=est["salud"]
    )
    enfermera.perfil.servicios.set([odonto])

    traza = services.trazabilidad(escenario["expediente"], enfermera)
    assert traza == [], f"se filtró: {traza}"


@pytest.mark.django_db
def test_direccion_tampoco_la_ve(escenario):
    """
    Ni Dirección, ni administración, ni break-glass. El sello no admite
    excepciones: es la regla que el Sprint 7 fijó y que no se negocia.
    """
    director = _ajeno("dir_traza", Rol.DIRECTOR)
    assert services.trazabilidad(escenario["expediente"], director) == []


@pytest.mark.django_db
def test_quien_derivó_sí_ve_su_propia_derivación_con_el_motivo(escenario):
    """
    La otra cara. El motivo lo escribió Medicina: ocultárselo a Medicina no
    protege a nadie y rompe el trabajo —no sabría qué derivó ni si le
    respondieron—.
    """
    traza = services.trazabilidad(escenario["expediente"], escenario["medico"])
    assert len(traza) == 1
    assert traza[0]["hacia"] == "Psicología"
    assert traza[0]["motivo"] == MOTIVO_SENSIBLE


@pytest.mark.django_db
def test_psicologia_ve_lo_que_le_derivaron(escenario):
    traza = services.trazabilidad(escenario["expediente"], escenario["psicologo"])
    assert len(traza) == 1
    assert traza[0]["motivo"] == MOTIVO_SENSIBLE


@pytest.mark.django_db
def test_una_derivacion_entre_servicios_abiertos_la_ve_cualquier_profesional(escenario):
    """
    La corrección se limita a lo confidencial. Una derivación de Medicina a
    Enfermería es gestión, y estrecharla de más dejaría el recorrido inútil
    para el resto de la Unidad.
    """
    from apps.core.models import Servicio

    est = escenario["est"]
    enfermeria = Servicio.objects.create(
        codigo="enfermeria", nombre="Enfermería", seccion=est["salud"]
    )
    services.derivar(
        escenario["atencion"], enfermeria, motivo="Control de presión", usuario=escenario["medico"]
    )
    otro, _ = crear_profesional("otro_traza", enfermeria, est["salud"])

    traza = services.trazabilidad(escenario["expediente"], otro)
    assert [t["hacia"] for t in traza] == ["Enfermería"]


@pytest.mark.django_db
def test_la_pantalla_no_imprime_el_motivo_sellado_a_quien_no_es_de_los_dos_servicios(escenario):
    """
    La plantilla imprimía `{{ t.motivo }}` y debajo escribía «El contenido de
    este servicio no es visible fuera de él», que era falso mientras lo
    imprimía justo encima.
    """
    from apps.core.models import Servicio

    est = escenario["est"]
    odonto = Servicio.objects.create(
        codigo="odontologia", nombre="Odontología", seccion=est["salud"]
    )
    ajeno, _ = crear_profesional("odo_traza", odonto, est["salud"])
    cliente = _cliente(ajeno)
    contenido = cliente.get(
        reverse("derivaciones:trazabilidad", args=[escenario["expediente"].pk])
    ).content.decode()
    assert MOTIVO_SENSIBLE not in contenido
    assert "Psicología" not in contenido
