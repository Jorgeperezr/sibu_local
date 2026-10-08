"""
El alta de personas con todo lo que se quiera guardar, sin obligar a nada.

El formulario solo ofrecía once casillas, y varios campos del modelo no tenían
por dónde entrar: género, identidad u orientación sexual, procedencia,
residencia, contacto de referencia, grupo sanguíneo y discapacidad. Dos de
ellos —género e identidad u orientación sexual— son variables del informe
estadístico, así que sin esta pantalla el informe solo podía llenarse desde una
carga masiva.

Lo que estas pruebas fijan sobre todo: que nada de eso sea obligatorio. Obligar
en el mostrador lleva a inventar el dato, y un dato inventado es peor que
ninguno.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.expediente.models import Expediente, Persona
from apps.expediente.services import registrar_persona
from apps.expediente.tests.factories import crear_estructura, crear_profesional

CLAVE = "clave-larga-12345"
CEDULA = "1104567894"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    usuario, _ = crear_profesional("medico_alta", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_alta", password=CLAVE)
    return {"usuario": usuario, "cliente": cliente}


MINIMO = {"cedula": CEDULA, "nombres": "María José", "apellidos": "Pérez Ríos"}


# ------------------------------------------------------- nada es obligatorio


@pytest.mark.django_db
def test_con_los_tres_datos_minimos_ya_se_registra(escenario):
    """Cédula, nombres y apellidos: lo que identifica a la persona y nada más."""
    expediente = registrar_persona(dict(MINIMO), usuario=escenario["usuario"])
    assert expediente.persona.cedula == CEDULA
    assert expediente.persona.genero == ""
    assert expediente.persona.procedencia == {}
    assert expediente.grupo_sanguineo == ""
    assert expediente.discapacidad_porcentaje is None


@pytest.mark.django_db
def test_guarda_genero_e_identidad_u_orientacion_sexual(escenario):
    """
    Las dos son variables del informe estadístico. Sin esta pantalla solo se
    podían llenar desde una carga masiva.
    """
    expediente = registrar_persona(
        {**MINIMO, "genero": "Femenino", "identidad_orientacion_sexual": "Bisexual"},
        usuario=escenario["usuario"],
    )
    assert expediente.persona.genero == "Femenino"
    assert expediente.persona.identidad_orientacion_sexual == "Bisexual"


@pytest.mark.django_db
def test_guarda_los_grupos_de_direccion_con_las_claves_de_la_ficha(escenario):
    """
    Las claves son las de `academico.mapping`, no unas propias: si difirieran,
    un dato escrito a mano y el mismo dato cargado desde matrícula acabarían en
    sitios distintos y ninguna pantalla los mostraría juntos.
    """
    expediente = registrar_persona(
        {
            **MINIMO,
            "procedencia-canton_procedencia": "Saraguro",
            "residencia-canton_actual": "Loja",
            "residencia-barrio_actual": "La Argelia",
            "referencia-representante_nombres": "Ana Pérez",
        },
        usuario=escenario["usuario"],
    )
    persona = expediente.persona
    assert persona.procedencia == {"canton_procedencia": "Saraguro"}
    assert persona.residencia_actual == {"canton_actual": "Loja", "barrio_actual": "La Argelia"}
    assert persona.contacto_referencia == {"representante_nombres": "Ana Pérez"}


@pytest.mark.django_db
def test_las_casillas_vacias_no_se_guardan(escenario):
    """
    Un diccionario lleno de cadenas vacías ocupa sitio, se exporta y se lee
    como «se preguntó y no había», que no es lo mismo que «no se preguntó».
    """
    expediente = registrar_persona(
        {
            **MINIMO,
            "procedencia-canton_procedencia": "  ",
            "procedencia-pais_procedencia": "Ecuador",
        },
        usuario=escenario["usuario"],
    )
    assert expediente.persona.procedencia == {"pais_procedencia": "Ecuador"}


@pytest.mark.django_db
def test_guarda_la_salud_basica_en_el_expediente(escenario):
    """Grupo sanguíneo y discapacidad viven en el expediente, no en la persona."""
    expediente = registrar_persona(
        {
            **MINIMO,
            "grupo_sanguineo": "O+",
            "discapacidad_tipo": "Física",
            "discapacidad_porcentaje": "45",
        },
        usuario=escenario["usuario"],
    )
    assert expediente.grupo_sanguineo == "O+"
    assert expediente.discapacidad_tipo == "Física"
    assert expediente.discapacidad_porcentaje == 45


# ------------------------------------------------------------- validaciones


@pytest.mark.django_db
def test_un_porcentaje_mayor_que_cien_avisa_en_vez_de_reventar(escenario):
    """
    `Expediente` lleva una CheckConstraint que lo limita a 100. Sin comprobarlo
    antes, un 150 tecleado por error saldría como IntegrityError —una pantalla
    de error 500— en vez de como un aviso corregible.
    """
    with pytest.raises(ValidationError, match="no puede pasar de 100"):
        registrar_persona(
            {**MINIMO, "discapacidad_porcentaje": "150"}, usuario=escenario["usuario"]
        )
    assert not Persona.objects.filter(cedula=CEDULA).exists()


@pytest.mark.django_db
def test_un_porcentaje_que_no_es_numero_avisa(escenario):
    with pytest.raises(ValidationError, match="número entero"):
        registrar_persona(
            {**MINIMO, "discapacidad_porcentaje": "mucho"}, usuario=escenario["usuario"]
        )


# ---------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_la_pantalla_ofrece_las_casillas_opcionales(escenario):
    contenido = escenario["cliente"].get(reverse("expediente:nuevo")).content.decode()
    for casilla in (
        'name="genero"',
        'name="identidad_orientacion_sexual"',
        'name="grupo_sanguineo"',
        'name="discapacidad_porcentaje"',
        'name="procedencia-canton_procedencia"',
        'name="residencia-barrio_actual"',
        'name="referencia-representante_telefono"',
        'name="telefono"',
    ):
        assert casilla in contenido, f"falta {casilla}"


@pytest.mark.django_db
def test_desde_la_pantalla_se_registra_con_solo_lo_obligatorio(escenario):
    escenario["cliente"].post(reverse("expediente:nuevo"), dict(MINIMO))
    assert Expediente.objects.filter(persona__cedula=CEDULA).exists()


@pytest.mark.django_db
def test_desde_la_pantalla_se_guardan_los_grupos(escenario):
    escenario["cliente"].post(
        reverse("expediente:nuevo"),
        {**MINIMO, "residencia-canton_actual": "Loja", "genero": "Femenino"},
    )
    persona = Persona.objects.get(cedula=CEDULA)
    assert persona.residencia_actual == {"canton_actual": "Loja"}
    assert persona.genero == "Femenino"


@pytest.mark.django_db
def test_si_el_alta_se_rechaza_no_se_pierde_lo_tecleado(escenario):
    """
    Con una cédula que no pasa el módulo 10 el formulario se vuelve a pintar.
    Sin devolver los valores, quien lo llenó perdería las treinta casillas.
    """
    respuesta = escenario["cliente"].post(
        reverse("expediente:nuevo"),
        {
            "cedula": "1104567890",  # inválida a propósito
            "nombres": "María José",
            "apellidos": "Pérez Ríos",
            "residencia-canton_actual": "Loja",
            "genero": "Femenino",
        },
        follow=True,
    )
    contenido = respuesta.content.decode()
    assert 'value="Loja"' in contenido
    assert 'value="Femenino"' in contenido
