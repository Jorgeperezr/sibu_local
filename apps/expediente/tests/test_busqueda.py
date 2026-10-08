"""
Búsqueda de expedientes por nombre, y el permiso que faltaba en la búsqueda.

Buscar exigía la cédula exacta: sin ella —que es lo normal cuando el paciente
llama por teléfono o llega sin documento— no había manera de dar con su
expediente desde la interfaz.

`buscar` era además la única de las tres vistas del expediente sin
`puede_ver_expediente`, y la consulta por cédula CREA la persona y su
expediente al resolver contra la fuente institucional.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.expediente.models import Expediente, Persona
from apps.expediente.selectors import buscar_personas
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, _ = crear_profesional("medico_busca", est["medicina"], est["salud"])
    estudiante = Usuario.objects.create_user(
        username="estudiante_busca", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    for usuario in (medico, estudiante):
        usuario.set_password(CLAVE)
        usuario.save()

    personas = []
    for cedula, nombres, apellidos in (
        ("1101002002", "María Fernanda", "Jaramillo Ochoa"),
        ("1103004006", "Luis Alberto", "Cueva Riofrío"),
        ("1105006009", "Ana Belén", "Jaramillo Guamán"),
    ):
        persona = Persona.objects.create(
            cedula=cedula,
            nombres=nombres,
            apellidos=apellidos,
            tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
        )
        personas.append(persona)
    # Solo las dos primeras tienen expediente abierto.
    for persona in personas[:2]:
        Expediente.objects.create(persona=persona, numero_expediente=f"EXP-{persona.cedula}")
    return {"medico": medico, "estudiante": estudiante, "personas": personas}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------------ selector


@pytest.mark.django_db
def test_encuentra_por_apellido(escenario):
    encontradas = list(buscar_personas("Jaramillo"))
    assert len(encontradas) == 2
    assert {p.cedula for p in encontradas} == {"1101002002", "1105006009"}


@pytest.mark.django_db
def test_encuentra_por_nombre_de_pila(escenario):
    assert [p.cedula for p in buscar_personas("Belén")] == ["1105006009"]


@pytest.mark.django_db
def test_todas_las_palabras_deben_coincidir(escenario):
    """«Jaramillo Ana» no puede devolver a María Fernanda Jaramillo."""
    assert [p.cedula for p in buscar_personas("Jaramillo Ana")] == ["1105006009"]


@pytest.mark.django_db
def test_no_distingue_mayusculas(escenario):
    assert len(list(buscar_personas("jaramillo"))) == 2


@pytest.mark.django_db
def test_con_menos_de_tres_letras_no_devuelve_nada(escenario):
    """Con dos letras la consulta devuelve medio padrón: no es una búsqueda."""
    assert list(buscar_personas("ja")) == []
    assert list(buscar_personas("")) == []


@pytest.mark.django_db
def test_buscar_por_nombre_no_crea_nada(escenario):
    """
    A diferencia de la búsqueda por cédula, esta no consulta al proveedor
    académico: no debe materializar personas ni expedientes.
    """
    antes = (Persona.objects.count(), Expediente.objects.count())
    list(buscar_personas("Jaramillo"))
    assert (Persona.objects.count(), Expediente.objects.count()) == antes


# ------------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_la_pantalla_lista_las_coincidencias(escenario):
    respuesta = _cliente(escenario["medico"]).get(
        reverse("expediente:buscar"), {"nombre": "Jaramillo"}
    )
    contenido = respuesta.content.decode()
    assert "Jaramillo Ochoa María Fernanda" in contenido
    assert "Cueva Riofrío" not in contenido


@pytest.mark.django_db
def test_quien_no_tiene_expediente_se_muestra_sin_enlace(escenario):
    contenido = (
        _cliente(escenario["medico"])
        .get(reverse("expediente:buscar"), {"nombre": "Ana Belén"})
        .content.decode()
    )
    assert "Jaramillo Guamán" in contenido
    assert "Sin expediente" in contenido


@pytest.mark.django_db
def test_sin_coincidencias_lo_dice(escenario):
    contenido = (
        _cliente(escenario["medico"])
        .get(reverse("expediente:buscar"), {"nombre": "Zambrano"}, follow=True)
        .content.decode()
    )
    assert "Ninguna persona registrada coincide" in contenido


@pytest.mark.django_db
def test_un_estudiante_no_entra_a_la_busqueda(escenario):
    """
    Era la única de las tres vistas del expediente sin el permiso, y la puerta
    de las otras dos: se consultaba cualquier cédula y se veían nombre,
    vínculo y datos académicos de cualquiera.
    """
    for parametros in ({"nombre": "Jaramillo"}, {"cedula": "1101002002"}, {}):
        respuesta = _cliente(escenario["estudiante"]).get(reverse("expediente:buscar"), parametros)
        assert respuesta.status_code == 403
