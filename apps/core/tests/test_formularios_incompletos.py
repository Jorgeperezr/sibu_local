"""
Un formulario incompleto avisa; no devuelve una página de error.

Las pantallas de trabajo leen sus campos con `request.POST["campo"]`. Ese
acceso directo lanza `MultiValueDictKeyError` —una subclase de `KeyError`—
cuando el campo no llega, y si el `except` de alrededor no lo contempla, el
profesional ve un error 500 en vez de «elija un código».

No es hipotético: pasa con un desplegable que quedó sin marcar, con un
autocompletado que no llegó a rellenar su campo oculto, y con cualquier envío
que no venga del formulario tal cual está pintado.

El patrón correcto ya estaba en el proyecto —Psicología y el `recetar` de
Medicina capturan `KeyError` junto a `ValidationError`— y seis pantallas de
cuatro servicios se lo habían dejado.

Esta prueba envía cada acción SIN ningún campo y exige que la pantalla
responda, no que reviente. No comprueba que el mensaje sea bueno; comprueba que
haya mensaje y no un 500.
"""

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

# (usuario, clave, nombre de la ruta, modelo del que sacar un id, acciones)
PANTALLAS = [
    (
        "jhoely.lalangui",
        "jhoely.lalangui",
        "medicina:consulta",
        "medicina.AtencionMedicina",
        ["guardar", "diagnostico", "recetar", "examenes", "cerrar"],
    ),
    (
        "daniel.cabrera",
        "daniel.cabrera",
        "odontologia:consulta",
        "odontologia.AtencionOdontologia",
        ["guardar", "diagnostico", "pieza", "procedimiento", "cerrar"],
    ),
    (
        "jorge.perez",
        "jorge.perez",
        "psicologia:proceso",
        "psicologia.FichaPsicologica",
        ["ficha", "sesion", "escala", "diagnostico", "riesgo", "cerrar"],
    ),
    (
        "farmaceutico",
        "sibu-demo-2026",
        "farmacia:despachar",
        "farmacia.Receta",
        ["despachar_item", "despachar_todo", "anular"],
    ),
    (
        "laboratorista",
        "sibu-demo-2026",
        "laboratorio:detalle",
        "laboratorio.OrdenLaboratorio",
        ["tomar_muestra", "resultado", "completar", "validar", "publicar", "rechazar_muestra"],
    ),
    (
        "becas",
        "sibu-demo-2026",
        "becas:ficha",
        "becas.BecaBeneficiario",
        ["verificar", "seguimiento", "estado"],
    ),
    (
        "jorge.perez",
        "jorge.perez",
        "talleres:detalle",
        "talleres.Taller",
        ["participante", "ejecutar", "evidencia", "cerrar"],
    ),
    (
        "trabajadora",
        "sibu-demo-2026",
        "trabajo_social:ficha",
        "expediente.Expediente",
        ["guardar", "verificar"],
    ),
]


@pytest.fixture
def sembrado(db, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def _primer_id(etiqueta):
    from django.apps import apps as registro

    modelo = registro.get_model(*etiqueta.split("."))
    fila = modelo.objects.first()
    return fila.pk if fila else None


def _casos():
    return [(u, c, n, m, a) for u, c, n, m, acciones in PANTALLAS for a in acciones]


@pytest.mark.django_db
def test_la_siembra_deja_algo_de_cada_cosa(sembrado):
    """
    Sin fila que abrir, cada caso se saltaría y la prueba pasaría afirmando
    nada. Esto exige que la siembra alimente al menos las pantallas clínicas.
    """
    faltan = [etiqueta for _u, _c, _n, etiqueta, _a in PANTALLAS if _primer_id(etiqueta) is None]
    assert faltan == [], f"la siembra no deja con qué probar: {faltan}"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "usuario,clave,ruta,etiqueta,accion",
    _casos(),
    ids=[f"{n.split(':')[0]}-{a}" for _u, _c, n, _m, a in _casos()],
)
def test_una_accion_sin_campos_no_devuelve_error_500(
    usuario, clave, ruta, etiqueta, accion, sembrado
):
    pk = _primer_id(etiqueta)
    assert pk is not None, f"la siembra no dejó ninguna fila de {etiqueta}"

    cliente = Client()
    assert cliente.login(username=usuario, password=clave), f"no entra {usuario}"

    respuesta = cliente.post(reverse(ruta, args=[pk]), {"accion": accion})
    assert (
        respuesta.status_code < 500
    ), f"{ruta} con accion={accion} y sin campos devolvió {respuesta.status_code}"
