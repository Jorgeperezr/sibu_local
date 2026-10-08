"""
Un ingreso escrito con coma es un ingreso.

Aquí se escribe 450,50. `Decimal(str("450,50"))` lanza `InvalidOperation`, que
la suma capturaba con un `continue`: el ingreso declarado se sumaba como CERO.
Nadie veía un error —ni la trabajadora social, ni el hogar— y el per cápita
bajaba, y con él el estrato, que es lo que orienta la asignación de una beca.

El campo del formulario es texto libre con `inputmode="decimal"`: en un
teclado en español eso ofrece la coma. No era un caso rebuscado, era el caso
normal.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.core.models import Servicio
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.trabajo_social import services
from apps.trabajo_social.models import FichaSocioeconomica

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    servicio, _ = Servicio.objects.get_or_create(
        codigo="trabajo-social", defaults={"nombre": "Trabajo Social", "seccion": est["salud"]}
    )
    trabajadora, perfil = crear_profesional("ts_coma", servicio, est["salud"])
    trabajadora.set_password(CLAVE)
    trabajadora.save()
    return {
        "est": est,
        "usuario": trabajadora,
        "perfil": perfil,
        "expediente": crear_expediente(cedula="1104567894"),
    }


def test_la_suma_lee_la_coma(db):
    ingresos, _ = services.calcular_totales(
        {"ingreso_padre": "450,50", "ingreso_madre": "300,25"}, {}
    )
    from decimal import Decimal

    assert ingresos == Decimal("750.75")


def test_la_coma_y_el_punto_dan_lo_mismo(db):
    con_coma, _ = services.calcular_totales({"ingreso_padre": "450,50"}, {})
    con_punto, _ = services.calcular_totales({"ingreso_padre": "450.50"}, {})
    assert con_coma == con_punto


def test_el_texto_descriptivo_de_una_ficha_vieja_no_revienta(db):
    """
    Las fichas cargadas arrastran «no aplica» donde debería ir un monto.

    Un cálculo sobre lo YA guardado no puede lanzar: se saltaría el puntaje de
    un expediente entero por una celda vieja.
    """
    from decimal import Decimal

    ingresos, _ = services.calcular_totales(
        {"ingreso_padre": "no aplica", "ingreso_madre": "300,25"}, {}
    )
    assert ingresos == Decimal("300.25")


def test_un_estrato_no_depende_de_como_se_escriba_el_numero(escenario):
    """La consecuencia concreta: el mismo hogar, dos formas de escribirlo."""

    def _puntaje(texto):
        ficha = FichaSocioeconomica(
            ingresos={"ingreso_padre": texto},
            egresos={},
            convivencia={"numero_miembros": "3"},
        )
        return services.calcular_puntaje(ficha)

    assert _puntaje("1200,00") == _puntaje("1200.00")
    _, estrato = _puntaje("1200,00")
    assert estrato != "Extrema vulnerabilidad"


def test_el_numero_de_miembros_con_texto_no_devuelve_una_pagina_de_error(db):
    """`int("tres")` lanzaba ValueError sin capturar."""
    ficha = FichaSocioeconomica(
        ingresos={"ingreso_padre": "300"}, egresos={}, convivencia={"numero_miembros": "tres"}
    )
    puntaje, _estrato = services.calcular_puntaje(ficha)
    assert puntaje is not None


def test_lo_que_se_acaba_de_escribir_si_se_valida(escenario):
    """
    Sobre lo guardado se es indulgente; sobre lo tecleado, no.

    Un «450,5O» con la letra O es un error de digitación: ignorarlo hace
    desaparecer ese ingreso del hogar.
    """
    with pytest.raises(ValidationError) as error:
        services.verificar_ficha(
            escenario["expediente"],
            {"ingresos": {"ingreso_padre": "450,5O"}, "egresos": {}, "convivencia": {}},
            profesional=escenario["perfil"],
            usuario=escenario["usuario"],
        )
    assert "450,5O" in " ".join(error.value.messages)
    assert not FichaSocioeconomica.objects.filter(expediente=escenario["expediente"]).exists()


@pytest.mark.django_db
def test_la_pantalla_avisa_en_vez_de_guardar_mal(escenario):
    cliente = Client()
    assert cliente.login(username=escenario["usuario"].username, password=CLAVE)
    respuesta = cliente.post(
        reverse("trabajo_social:ficha", args=[escenario["expediente"].pk]),
        {"ingreso-ingreso_padre": "450,5O", "numero_miembros": "3"},
        follow=True,
    )
    assert respuesta.status_code == 200
    assert "no es un número" in respuesta.content.decode()


@pytest.mark.django_db
def test_una_ficha_con_coma_se_guarda_con_el_valor_que_se_escribio(escenario):
    from decimal import Decimal

    cliente = Client()
    assert cliente.login(username=escenario["usuario"].username, password=CLAVE)
    cliente.post(
        reverse("trabajo_social:ficha", args=[escenario["expediente"].pk]),
        {"ingreso-ingreso_padre": "450,50", "numero_miembros": "1"},
        follow=True,
    )
    ficha = FichaSocioeconomica.objects.get(expediente=escenario["expediente"], vigente=True)
    ingresos, _ = services.calcular_totales(ficha.ingresos, ficha.egresos)
    assert ingresos == Decimal("450.50")


@pytest.mark.django_db
def test_una_verificacion_a_medias_no_deja_la_ficha_partida(escenario, monkeypatch):
    """
    `verificar_ficha` desmarca la vigente y crea la siguiente: si falla entre
    los dos pasos y no es atómica, el expediente queda SIN ficha vigente y el
    puntaje desaparece.

    Se comprueba el comportamiento y no el decorador porque es el
    comportamiento lo que importa —y porque un `@transaction.atomic` es fácil
    de desplazar sin querer al insertar una función encima de la que decoraba—.
    """
    services.verificar_ficha(
        escenario["expediente"],
        {"ingresos": {"ingreso_padre": "100"}, "egresos": {}, "convivencia": {}},
        profesional=escenario["perfil"],
        usuario=escenario["usuario"],
    )
    primera = FichaSocioeconomica.objects.get(expediente=escenario["expediente"], vigente=True)

    def _revienta(*_args, **_kwargs):
        raise RuntimeError("fallo a mitad de la verificación")

    monkeypatch.setattr(services, "calcular_puntaje", _revienta)
    with pytest.raises(RuntimeError):
        services.verificar_ficha(
            escenario["expediente"],
            {"ingresos": {"ingreso_padre": "200"}, "egresos": {}, "convivencia": {}},
            profesional=escenario["perfil"],
            usuario=escenario["usuario"],
        )

    vigentes = FichaSocioeconomica.objects.filter(expediente=escenario["expediente"], vigente=True)
    assert vigentes.count() == 1
    assert vigentes.first().pk == primera.pk
