"""Pruebas de emisión de recetas desde la consulta médica."""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import CIE10
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.farmacia import services
from apps.farmacia.models import Medicamento, Receta
from apps.medicina import services as med_services


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567894")
    CIE10.objects.get_or_create(codigo="J00", defaults={"descripcion": "Resfriado"})
    paracetamol = Medicamento.objects.create(
        codigo="MED-001",
        dci="Paracetamol",
        concentracion="500 mg",
        forma_farmaceutica="Tableta",
        unidad_medida="tableta",
    )
    hc = med_services.crear_atencion_medicina(
        expediente=exp,
        profesional=medico,
        motivo="Fiebre",
    )
    return {"est": est, "medico": medico, "exp": exp, "med": paracetamol, "hc": hc}


@pytest.mark.django_db
def test_emitir_receta_genera_numero_y_vigencia(escenario):
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [
            {
                "medicamento_id": escenario["med"].id,
                "cantidad_prescrita": 20,
                "dosis": "1 tableta",
                "via": "oral",
                "frecuencia": "cada 8h",
                "duracion": "5 días",
            }
        ],
    )
    assert receta.numero.startswith(f"RX-{timezone.now().year}-")
    assert receta.estado == Receta.Estado.EMITIDA
    assert receta.valida_hasta > timezone.now()
    assert receta.detalles.count() == 1


@pytest.mark.django_db
def test_numeracion_correlativa(escenario):
    r1 = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 10}],
    )
    r2 = services.emitir_receta(
        escenario["hc"].atencion, [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 5}]
    )
    assert int(r2.numero.split("-")[-1]) == int(r1.numero.split("-")[-1]) + 1


@pytest.mark.django_db
def test_receta_vacia_rechazada(escenario):
    with pytest.raises(ValidationError, match="al menos un medicamento"):
        services.emitir_receta(escenario["hc"].atencion, [])


@pytest.mark.django_db
def test_cantidad_cero_rechazada(escenario):
    with pytest.raises(ValidationError, match="mayor a cero"):
        services.emitir_receta(
            escenario["hc"].atencion,
            [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 0}],
        )


@pytest.mark.django_db
def test_no_emitir_sobre_atencion_firmada(escenario):
    atencion = escenario["hc"].atencion
    atencion.estado = Atencion.Estado.FIRMADA
    atencion.save()
    with pytest.raises(ValidationError, match="firmada"):
        services.emitir_receta(
            atencion, [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 10}]
        )


@pytest.mark.django_db
def test_caducar_recetas_vencidas(escenario):
    from datetime import timedelta

    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 10}],
    )
    receta.valida_hasta = timezone.now() - timedelta(hours=1)
    receta.save()
    assert services.caducar_recetas_vencidas() == 1
    receta.refresh_from_db()
    assert receta.estado == Receta.Estado.CADUCADA
    assert services.recetas_pendientes().count() == 0
