"""Pruebas de inventario y despacho FEFO."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import CIE10
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.farmacia import services
from apps.farmacia.models import Lote, Medicamento, MovimientoInventario, Receta
from apps.medicina import services as med_services


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    _, quimico = crear_profesional("quimico", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567894")
    CIE10.objects.get_or_create(codigo="J00", defaults={"descripcion": "Resfriado"})

    paracetamol = Medicamento.objects.create(
        codigo="MED-001",
        dci="Paracetamol",
        concentracion="500 mg",
        unidad_medida="tableta",
        stock_minimo=50,
    )
    hc = med_services.crear_atencion_medicina(expediente=exp, profesional=medico, motivo="Fiebre")
    return {
        "est": est,
        "medico": medico,
        "quimico": quimico,
        "exp": exp,
        "med": paracetamol,
        "hc": hc,
    }


def _fecha(dias):
    return timezone.localdate() + timedelta(days=dias)


@pytest.mark.django_db
def test_ingresar_lote_crea_movimiento(escenario):
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["quimico"]
    )
    assert lote.cantidad_actual == 100
    mov = MovimientoInventario.objects.get(lote=lote)
    assert mov.tipo == MovimientoInventario.Tipo.INGRESO
    assert mov.saldo_resultante == 100


@pytest.mark.django_db
def test_ingresar_lote_caducado_rechazado(escenario):
    with pytest.raises(ValidationError, match="caducado"):
        services.ingresar_lote(
            escenario["med"], "L-VIEJO", 50, _fecha(-1), usuario=escenario["quimico"]
        )


@pytest.mark.django_db
def test_mismo_lote_dos_caducidades_rechazado(escenario):
    services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["quimico"]
    )
    with pytest.raises(ValidationError, match="dos fechas de caducidad"):
        services.ingresar_lote(
            escenario["med"], "L-001", 50, _fecha(200), usuario=escenario["quimico"]
        )


@pytest.mark.django_db
def test_reingreso_del_mismo_lote_suma(escenario):
    services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["quimico"]
    )
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 50, _fecha(365), usuario=escenario["quimico"]
    )
    assert lote.cantidad_actual == 150
    assert MovimientoInventario.objects.filter(lote=lote).count() == 2


@pytest.mark.django_db
def test_stock_disponible_excluye_caducados(escenario):
    services.ingresar_lote(
        escenario["med"], "L-BUENO", 100, _fecha(365), usuario=escenario["quimico"]
    )
    # Lote caducado insertado directamente (ingresar_lote lo rechazaría)
    Lote.objects.create(
        medicamento=escenario["med"],
        numero_lote="L-CADUCO",
        fecha_caducidad=_fecha(-10),
        cantidad_actual=999,
    )
    assert services.stock_disponible(escenario["med"]) == 100


@pytest.mark.django_db
def test_fefo_consume_el_lote_que_caduca_antes(escenario):
    """La regla central: primero sale lo que caduca antes, sin importar el orden de ingreso."""
    # Se ingresa PRIMERO el de caducidad lejana
    services.ingresar_lote(
        escenario["med"], "L-LEJANO", 100, _fecha(365), usuario=escenario["quimico"]
    )
    # Y DESPUÉS uno que caduca pronto
    services.ingresar_lote(
        escenario["med"], "L-PRONTO", 30, _fecha(30), usuario=escenario["quimico"]
    )

    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20}],
    )
    detalle = receta.detalles.first()
    dispensaciones = services.despachar_item(detalle, 20, usuario=escenario["quimico"])

    assert len(dispensaciones) == 1
    assert dispensaciones[0].lote.numero_lote == "L-PRONTO"  # FEFO, no FIFO

    lote_pronto = Lote.objects.get(numero_lote="L-PRONTO")
    lote_lejano = Lote.objects.get(numero_lote="L-LEJANO")
    assert lote_pronto.cantidad_actual == 10
    assert lote_lejano.cantidad_actual == 100  # intacto


@pytest.mark.django_db
def test_fefo_reparte_entre_lotes_cuando_no_alcanza(escenario):
    services.ingresar_lote(
        escenario["med"], "L-PRONTO", 30, _fecha(30), usuario=escenario["quimico"]
    )
    services.ingresar_lote(
        escenario["med"], "L-MEDIO", 50, _fecha(90), usuario=escenario["quimico"]
    )

    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 45}],
    )
    detalle = receta.detalles.first()
    dispensaciones = services.despachar_item(detalle, 45, usuario=escenario["quimico"])

    assert len(dispensaciones) == 2
    assert dispensaciones[0].lote.numero_lote == "L-PRONTO"
    assert dispensaciones[0].cantidad_despachada == 30  # agota el primero
    assert dispensaciones[1].lote.numero_lote == "L-MEDIO"
    assert dispensaciones[1].cantidad_despachada == 15  # completa del segundo

    assert Lote.objects.get(numero_lote="L-PRONTO").cantidad_actual == 0
    assert Lote.objects.get(numero_lote="L-MEDIO").cantidad_actual == 35


@pytest.mark.django_db
def test_no_despachar_mas_de_lo_prescrito(escenario):
    services.ingresar_lote(
        escenario["med"], "L-001", 500, _fecha(365), usuario=escenario["quimico"]
    )
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20}],
    )
    detalle = receta.detalles.first()
    with pytest.raises(ValidationError, match="Solo quedan 20"):
        services.despachar_item(detalle, 25, usuario=escenario["quimico"])


@pytest.mark.django_db
def test_no_despachar_sin_stock(escenario):
    services.ingresar_lote(escenario["med"], "L-001", 5, _fecha(365), usuario=escenario["quimico"])
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20}],
    )
    detalle = receta.detalles.first()
    with pytest.raises(ValidationError, match="Stock insuficiente"):
        services.despachar_item(detalle, 20, usuario=escenario["quimico"])


@pytest.mark.django_db
def test_despacho_parcial_y_completo_actualiza_estado(escenario):
    services.ingresar_lote(
        escenario["med"], "L-001", 500, _fecha(365), usuario=escenario["quimico"]
    )
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20}],
    )
    detalle = receta.detalles.first()

    services.despachar_item(detalle, 12, usuario=escenario["quimico"])
    receta.refresh_from_db()
    assert receta.estado == Receta.Estado.PARCIAL
    assert services.pendiente_por_despachar(detalle) == 8

    services.despachar_item(detalle, 8, usuario=escenario["quimico"])
    receta.refresh_from_db()
    assert receta.estado == Receta.Estado.DESPACHADA
    assert services.pendiente_por_despachar(detalle) == 0


@pytest.mark.django_db
def test_no_despachar_receta_caducada(escenario):
    services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["quimico"]
    )
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20}],
    )
    receta.valida_hasta = timezone.now() - timedelta(hours=1)
    receta.save()
    with pytest.raises(ValidationError, match="caducó"):
        services.despachar_item(receta.detalles.first(), 10, usuario=escenario["quimico"])


@pytest.mark.django_db
def test_despachar_receta_completa_reporta_faltantes(escenario):
    """Entrega lo que hay y reporta el faltante, sin fallar."""
    otro = Medicamento.objects.create(codigo="MED-002", dci="Ibuprofeno", concentracion="400 mg")
    services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["quimico"]
    )
    services.ingresar_lote(otro, "L-002", 5, _fecha(365), usuario=escenario["quimico"])

    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [
            {"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20},
            {"medicamento_id": otro.id, "cantidad_prescrita": 30},
        ],
    )
    resumen = services.despachar_receta_completa(receta, usuario=escenario["quimico"])

    assert len(resumen["despachado"]) == 2
    assert len(resumen["sin_stock"]) == 1
    assert resumen["sin_stock"][0]["faltante"] == 25
    receta.refresh_from_db()
    assert receta.estado == Receta.Estado.PARCIAL


@pytest.mark.django_db
def test_alertas_stock_minimo(escenario):
    services.ingresar_lote(escenario["med"], "L-001", 40, _fecha(365), usuario=escenario["quimico"])
    alertas = services.alertas_stock()
    assert len(alertas) == 1
    assert alertas[0]["disponible"] == 40
    assert alertas[0]["minimo"] == 50
    assert alertas[0]["critico"] is False


@pytest.mark.django_db
def test_alertas_caducidad_proxima(escenario):
    services.ingresar_lote(
        escenario["med"], "L-PRONTO", 10, _fecha(30), usuario=escenario["quimico"]
    )
    services.ingresar_lote(
        escenario["med"], "L-LEJANO", 10, _fecha(365), usuario=escenario["quimico"]
    )
    alertas = list(services.alertas_caducidad(dias=90))
    assert len(alertas) == 1
    assert alertas[0].numero_lote == "L-PRONTO"


@pytest.mark.django_db
def test_dar_de_baja_caducados(escenario):
    Lote.objects.create(
        medicamento=escenario["med"],
        numero_lote="L-CADUCO",
        fecha_caducidad=_fecha(-5),
        cantidad_actual=25,
    )
    unidades = services.dar_de_baja_caducados(escenario["quimico"])
    assert unidades == 25
    assert Lote.objects.get(numero_lote="L-CADUCO").cantidad_actual == 0
    assert MovimientoInventario.objects.filter(tipo=MovimientoInventario.Tipo.BAJA).exists()


@pytest.mark.django_db
def test_anular_receta_no_despachada(escenario):
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20}],
    )
    services.anular_receta(receta, "Error de prescripción")
    assert receta.estado == Receta.Estado.ANULADA


@pytest.mark.django_db
def test_no_anular_receta_ya_despachada(escenario):
    services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["quimico"]
    )
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20}],
    )
    services.despachar_item(receta.detalles.first(), 10, usuario=escenario["quimico"])
    with pytest.raises(ValidationError, match="ya despachada"):
        services.anular_receta(receta, "tardío")


@pytest.mark.django_db
def test_trazabilidad_saldo_reconstruible(escenario):
    """El saldo del lote debe poder reconstruirse desde los movimientos."""
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["quimico"]
    )
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 30}],
    )
    services.despachar_item(receta.detalles.first(), 30, usuario=escenario["quimico"])

    movimientos = MovimientoInventario.objects.filter(lote=lote).order_by("id")
    saldo = sum(m.cantidad for m in movimientos)
    lote.refresh_from_db()
    assert saldo == lote.cantidad_actual == 70
    assert movimientos.last().saldo_resultante == 70


# ==========================================================================
# Concurrencia: el stock se comprobaba antes de bloquear los lotes
# ==========================================================================


@pytest.mark.django_db
def test_el_despacho_aborta_si_el_stock_se_agota_entre_la_lectura_y_el_consumo(escenario):
    """
    Simula la carrera: dos despachos leen el mismo stock disponible, ambos
    pasan la validación y el segundo se encuentra los lotes ya vacíos.

    Antes, el bucle terminaba con `restante > 0` sin decir nada: quedaban
    dispensaciones por menos de lo pedido mientras el llamador daba por
    entregada la cantidad completa. Ahora aborta y no deja entrega a medias.
    """
    from unittest.mock import patch

    services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["quimico"]
    )
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 20}],
    )
    detalle = receta.detalles.first()

    # `lotes_fefo` sin resultados es lo que ve el segundo despacho cuando el
    # primero ya consumió todo entre la comprobación y el consumo.
    with patch("apps.farmacia.services.lotes_fefo") as fefo:
        fefo.return_value = Lote.objects.none()
        with pytest.raises(ValidationError, match="Stock insuficiente"):
            services.despachar_item(detalle, 20, usuario=escenario["quimico"])

    assert not detalle.dispensaciones.exists()


@pytest.mark.django_db
def test_no_se_despacha_mas_de_lo_prescrito_aunque_sobre_stock(escenario):
    """El pendiente se cuenta con el detalle bloqueado, no a ojo."""
    services.ingresar_lote(
        escenario["med"], "L-001", 500, _fecha(365), usuario=escenario["quimico"]
    )
    receta = services.emitir_receta(
        escenario["hc"].atencion,
        [{"medicamento_id": escenario["med"].id, "cantidad_prescrita": 10}],
    )
    detalle = receta.detalles.first()
    services.despachar_item(detalle, 6, usuario=escenario["quimico"])

    # Quedan 4 pendientes y stock de sobra: el límite es la receta, no el stock.
    with pytest.raises(ValidationError, match="Solo quedan 4"):
        services.despachar_item(detalle, 6, usuario=escenario["quimico"])


# ==========================================================================
# Coste en consultas: constante, no proporcional al catálogo
# ==========================================================================


@pytest.mark.django_db
def test_las_alertas_de_stock_no_crecen_con_el_catalogo(escenario, django_assert_num_queries):
    """
    Antes se preguntaba el stock medicamento por medicamento: 21 consultas para
    20 medicamentos, y la farmacia real tiene cientos en cada carga del
    mostrador. Ahora el agregado se hace en la base.
    """
    for i in range(20):
        Medicamento.objects.create(codigo=f"MED-N{i}", dci=f"Fármaco {i}", stock_minimo=10)

    with django_assert_num_queries(2):
        services.alertas_stock()


@pytest.mark.django_db
def test_el_estado_de_la_receta_se_recalcula_en_dos_consultas(escenario, django_assert_num_queries):
    """Se preguntaba dos veces por línea, y esto corre en cada despacho."""
    items = []
    for i in range(10):
        med = Medicamento.objects.create(codigo=f"MED-R{i}", dci=f"Fármaco {i}")
        items.append({"medicamento_id": med.id, "cantidad_prescrita": 5})
    receta = services.emitir_receta(escenario["hc"].atencion, items)

    with django_assert_num_queries(2):
        services._actualizar_estado_receta(receta)


@pytest.mark.django_db
def test_el_agregado_por_medicamento_coincide_con_el_individual(escenario):
    """
    La consulta agregada tiene que dar exactamente lo mismo que preguntar uno a
    uno: mismo filtro de caducidad y de existencias.
    """
    otro = Medicamento.objects.create(codigo="MED-OTRO", dci="Otro")
    services.ingresar_lote(escenario["med"], "L-A", 30, _fecha(365), usuario=escenario["quimico"])
    services.ingresar_lote(escenario["med"], "L-B", 12, _fecha(30), usuario=escenario["quimico"])

    por_medicamento = services.stock_disponible_por_medicamento()
    assert por_medicamento[escenario["med"].pk] == services.stock_disponible(escenario["med"])
    # Sin existencias no aparece en el diccionario: la ausencia vale 0.
    assert otro.pk not in por_medicamento
    assert services.stock_disponible(otro) == 0
