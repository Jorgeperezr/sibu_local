"""
Recetar y pedir exámenes desde la consulta médica.

`farmacia.emitir_receta` y `laboratorio.crear_orden` existían desde los
Sprints 4 y 6, pero la pantalla de consulta solo los MOSTRABA: para emitir una
receta había que llamar a la API a mano —la propia plantilla lo confesaba,
imprimiendo la URL del endpoint—. Es el mismo hueco que tenía la derivación.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.core.models import CIE10
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.farmacia import services as farmacia_services
from apps.farmacia.models import Medicamento, Receta
from apps.laboratorio.models import Examen, OrdenLaboratorio
from apps.medicina import services as med_services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil = crear_profesional("medico_consulta", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()
    exp = crear_expediente(cedula="1104567894")
    CIE10.objects.get_or_create(codigo="J00", defaults={"descripcion": "Resfriado"})
    hc = med_services.crear_atencion_medicina(expediente=exp, profesional=perfil, motivo="Fiebre")
    paracetamol = Medicamento.objects.create(
        codigo="MED-001", dci="Paracetamol", concentracion="500 mg", unidad_medida="tableta"
    )
    ibuprofeno = Medicamento.objects.create(
        codigo="MED-002", dci="Ibuprofeno", concentracion="400 mg", unidad_medida="tableta"
    )
    biometria = Examen.objects.create(codigo="LAB-001", nombre="Biometría hemática")
    return {
        "medico": medico,
        "perfil": perfil,
        "hc": hc,
        "paracetamol": paracetamol,
        "ibuprofeno": ibuprofeno,
        "biometria": biometria,
    }


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


def _url(escenario):
    return reverse("medicina:consulta", args=[escenario["hc"].pk])


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_agregar_medicamento_a_una_receta_abierta(escenario):
    receta = farmacia_services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["paracetamol"].pk, "cantidad_prescrita": 9}],
    )
    farmacia_services.agregar_medicamento(
        receta, {"medicamento_id": escenario["ibuprofeno"].pk, "cantidad_prescrita": 6}
    )
    assert receta.detalles.count() == 2


@pytest.mark.django_db
def test_no_se_repite_el_mismo_medicamento_en_una_receta(escenario):
    receta = farmacia_services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["paracetamol"].pk, "cantidad_prescrita": 9}],
    )
    with pytest.raises(ValidationError, match="ya consta"):
        farmacia_services.agregar_medicamento(
            receta, {"medicamento_id": escenario["paracetamol"].pk, "cantidad_prescrita": 3}
        )


@pytest.mark.django_db
def test_no_se_agrega_a_una_receta_ya_despachada(escenario):
    """
    Cambiar lo prescrito después de una entrega dejaría la receta sin
    corresponder con lo que se entregó.
    """
    from datetime import timedelta

    from django.utils import timezone

    receta = farmacia_services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["paracetamol"].pk, "cantidad_prescrita": 9}],
    )
    farmacia_services.ingresar_lote(
        escenario["paracetamol"],
        "L-001",
        50,
        timezone.localdate() + timedelta(days=365),
        usuario=escenario["perfil"],
    )
    farmacia_services.despachar_item(receta.detalles.first(), 9, usuario=escenario["perfil"])
    # Se fija el comportamiento, no el texto: normalmente frena el estado de la
    # receta, y la comprobación de entregas es la segunda línea por si ese
    # estado quedara desfasado.
    with pytest.raises(ValidationError):
        farmacia_services.agregar_medicamento(
            receta, {"medicamento_id": escenario["ibuprofeno"].pk, "cantidad_prescrita": 6}
        )
    assert receta.detalles.count() == 1


@pytest.mark.django_db
def test_receta_abierta_ignora_las_ya_despachadas(escenario):
    from datetime import timedelta

    from django.utils import timezone

    receta = farmacia_services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["paracetamol"].pk, "cantidad_prescrita": 9}],
    )
    assert farmacia_services.receta_abierta(escenario["hc"].atencion) == receta

    farmacia_services.ingresar_lote(
        escenario["paracetamol"],
        "L-001",
        50,
        timezone.localdate() + timedelta(days=365),
        usuario=escenario["perfil"],
    )
    farmacia_services.despachar_item(receta.detalles.first(), 5, usuario=escenario["perfil"])
    assert farmacia_services.receta_abierta(escenario["hc"].atencion) is None


# ------------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_recetar_desde_la_consulta(escenario):
    _cliente(escenario["medico"]).post(
        _url(escenario),
        {
            "accion": "recetar",
            "medicamento": escenario["paracetamol"].pk,
            "cantidad": "9",
            "dosis": "1 tableta",
            "frecuencia": "cada 8 h",
            "duracion": "3 días",
        },
    )
    receta = Receta.objects.get(atencion=escenario["hc"].atencion)
    detalle = receta.detalles.get()
    assert detalle.medicamento == escenario["paracetamol"]
    assert detalle.cantidad_prescrita == 9
    assert detalle.frecuencia == "cada 8 h"


@pytest.mark.django_db
def test_el_segundo_medicamento_va_a_la_misma_receta(escenario):
    """
    Una consulta emite UNA receta con varios medicamentos, no una receta por
    medicamento.
    """
    cliente = _cliente(escenario["medico"])
    for medicamento in (escenario["paracetamol"], escenario["ibuprofeno"]):
        cliente.post(
            _url(escenario),
            {"accion": "recetar", "medicamento": medicamento.pk, "cantidad": "6"},
        )
    assert Receta.objects.filter(atencion=escenario["hc"].atencion).count() == 1
    assert Receta.objects.get(atencion=escenario["hc"].atencion).detalles.count() == 2


@pytest.mark.django_db
def test_una_cantidad_cero_se_rechaza_y_no_deja_receta(escenario):
    respuesta = _cliente(escenario["medico"]).post(
        _url(escenario),
        {"accion": "recetar", "medicamento": escenario["paracetamol"].pk, "cantidad": "0"},
        follow=True,
    )
    assert "mayor a cero" in respuesta.content.decode()
    assert not Receta.objects.filter(atencion=escenario["hc"].atencion).exists()


@pytest.mark.django_db
def test_solicitar_examenes_desde_la_consulta(escenario):
    _cliente(escenario["medico"]).post(
        _url(escenario),
        {
            "accion": "examenes",
            "examenes": [escenario["biometria"].pk],
            "prioridad": "urgente",
        },
    )
    orden = OrdenLaboratorio.objects.get(atencion=escenario["hc"].atencion)
    assert orden.prioridad == "urgente"
    assert [oe.examen for oe in orden.examenes.all()] == [escenario["biometria"]]


@pytest.mark.django_db
def test_sin_examenes_seleccionados_avisa(escenario):
    respuesta = _cliente(escenario["medico"]).post(
        _url(escenario), {"accion": "examenes", "examenes": []}, follow=True
    )
    assert "al menos un examen" in respuesta.content.decode()
    assert not OrdenLaboratorio.objects.filter(atencion=escenario["hc"].atencion).exists()


@pytest.mark.django_db
def test_una_atencion_firmada_no_ofrece_los_formularios(escenario):
    escenario["hc"].atencion.estado = Atencion.Estado.FIRMADA
    escenario["hc"].atencion.save(update_fields=["estado"])
    contenido = _cliente(escenario["medico"]).get(_url(escenario)).content.decode()
    assert 'value="recetar"' not in contenido
    assert 'value="examenes"' not in contenido
