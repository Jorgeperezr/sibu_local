"""
La pantalla de la ficha socioeconómica.

Tres defectos que costaban datos y que estas pruebas fijan:

1. Las casillas salían vacías y el formulario reconstruía el diccionario
   entero. Pulsar «Registrar verificación» sin tocar nada dejaba los ingresos
   en `{}`, el puntaje caía a cero y el estudiante pasaba a «Extrema
   vulnerabilidad» sin que nadie lo hubiera afirmado.
2. Lo que la ficha de matrícula trae pero la pantalla no dibuja —quién financia
   los estudios, el detalle de una deuda— desaparecía al guardar.
3. Los totales que el propio estudiante declaró se sumaban junto a sus
   componentes, duplicando el ingreso del hogar.

Todo esto importa porque el puntaje orienta la asignación de una beca.
"""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import Servicio
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.trabajo_social import services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    ts, _ = Servicio.objects.get_or_create(
        codigo="trabajo-social", defaults={"nombre": "Trabajo Social", "seccion": est["salud"]}
    )
    usuario, perfil = crear_profesional("ts_web", ts, ts.seccion)
    usuario.set_password(CLAVE)
    usuario.save()
    expediente = crear_expediente(cedula="1104567894")
    expediente.persona.residencia_actual = {"canton": "Loja", "viv_est_tipo": "Arrendada"}
    expediente.persona.save()

    ficha = services.prepoblar_desde_matricula(expediente)
    ficha.ingresos = {"ingreso_padre": "400", "ingreso_madre": "300"}
    ficha.egresos = {"gastos_vivienda": "150", "quien_financia_estudios": "El padre"}
    ficha.convivencia = {
        "estudiante_necesidades_educativas_especiales": "Sí",
        "numero_miembros": "4",
    }
    ficha.save()

    cliente = Client()
    assert cliente.login(username="ts_web", password=CLAVE)
    return {"exp": expediente, "cliente": cliente, "perfil": perfil, "ficha": ficha}


def _url(escenario):
    return reverse("trabajo_social:ficha", args=[escenario["exp"].pk])


# ------------------------------------------------------------------ pantalla


@pytest.mark.django_db
def test_las_casillas_salen_con_lo_que_la_ficha_ya_tiene(escenario):
    contenido = escenario["cliente"].get(_url(escenario)).content.decode()
    assert 'name="ingreso-ingreso_padre" value="400"' in contenido
    assert 'name="egreso-gastos_vivienda" value="150"' in contenido


@pytest.mark.django_db
def test_guardar_sin_tocar_nada_no_borra_los_ingresos(escenario):
    """
    El defecto que motivó todo esto: el puntaje que orienta una beca caía a
    cero porque el formulario mandaba un diccionario vacío.
    """
    escenario["cliente"].post(
        _url(escenario),
        {
            "numero_miembros": "4",
            "ingreso-ingreso_padre": "400",
            "ingreso-ingreso_madre": "300",
            "egreso-gastos_vivienda": "150",
        },
    )
    v2 = services.ficha_vigente(escenario["exp"])
    assert v2.version == 2
    assert v2.ingresos == {"ingreso_padre": "400", "ingreso_madre": "300"}
    assert v2.ingresos_totales == Decimal("700")
    # Con el defecto, `ingresos_totales` quedaba en 0 y el puntaje también.
    assert v2.puntaje > Decimal("0")


@pytest.mark.django_db
def test_lo_que_la_pantalla_no_dibuja_se_conserva(escenario):
    """
    `quien_financia_estudios` viene de matrícula y no tiene casilla. Antes se
    perdía al guardar, sin aviso.
    """
    escenario["cliente"].post(
        _url(escenario), {"numero_miembros": "4", "egreso-gastos_vivienda": "150"}
    )
    v2 = services.ficha_vigente(escenario["exp"])
    assert v2.egresos["quien_financia_estudios"] == "El padre"


@pytest.mark.django_db
def test_el_numero_de_miembros_no_borra_el_resto_de_la_convivencia(escenario):
    """
    La necesidad educativa especial declarada en matrícula vive en
    `convivencia`. Reemplazar el grupo entero por el número de miembros la
    borraba, y con ella el motivo por el que Psicopedagogía tenía una alerta.
    """
    escenario["cliente"].post(_url(escenario), {"numero_miembros": "5"})
    v2 = services.ficha_vigente(escenario["exp"])
    assert v2.convivencia["estudiante_necesidades_educativas_especiales"] == "Sí"
    assert v2.convivencia["numero_miembros"] == "5"


@pytest.mark.django_db
def test_vaciar_una_casilla_si_borra_ese_dato(escenario):
    """
    Conservar lo no dibujado no puede convertirse en «nada se borra nunca»: si
    el profesional vacía una casilla que sí ve, es porque quiere quitarla.
    """
    escenario["cliente"].post(
        _url(escenario),
        {"numero_miembros": "4", "ingreso-ingreso_padre": "400", "ingreso-ingreso_madre": ""},
    )
    v2 = services.ficha_vigente(escenario["exp"])
    assert "ingreso_madre" not in v2.ingresos
    assert v2.ingresos["ingreso_padre"] == "400"


@pytest.mark.django_db
def test_la_pantalla_muestra_lo_declarado_en_matricula(escenario):
    contenido = escenario["cliente"].get(_url(escenario)).content.decode()
    assert "Convivencia y entorno académico" in contenido
    assert "Estudiante necesidades educativas especiales" in contenido


# -------------------------------------------------------------------- totales


@pytest.mark.django_db
def test_el_total_declarado_no_se_suma_con_sus_componentes(escenario):
    """
    `ingreso_mensual` es la suma que declaró el estudiante, no una línea más.
    Contarla junto a sus componentes duplicaba el ingreso del hogar.
    """
    ingresos, egresos = services.calcular_totales(
        {"ingreso_padre": "400", "ingreso_madre": "300", "ingreso_mensual": "700"},
        {"gastos_vivienda": "150", "gastos_mensual_familia": "150"},
    )
    assert ingresos == Decimal("700")
    assert egresos == Decimal("150")


@pytest.mark.django_db
def test_el_estrato_no_se_desplaza_por_el_total_duplicado(escenario):
    """
    No es un redondeo, y va en la dirección que más daño hace: al contar dos
    veces lo mismo el hogar parecía tener el doble de ingreso, así que un hogar
    de dos con 700 al mes salía de «Vulnerabilidad alta» y aparecía como
    «Vulnerabilidad media», por debajo del tramo que la Unidad prioriza.
    """
    v2 = services.verificar_ficha(
        escenario["exp"],
        {
            "ingresos": {"ingreso_padre": "400", "ingreso_madre": "300", "ingreso_mensual": "700"},
            "convivencia": {"numero_miembros": "2"},
        },
        profesional=escenario["perfil"],
    )
    assert v2.ingresos_totales == Decimal("700")
    assert v2.estrato == "Vulnerabilidad alta"
