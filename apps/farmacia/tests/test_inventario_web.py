"""
Ingreso de lotes y ajustes de inventario desde la web.

Hasta ahora el inventario solo se movía por el shell o por el panel de
administración, que escribe el saldo directamente y no deja movimiento: el
saldo dejaba de poder reconstruirse desde la bitácora, que es justo lo que
exige la trazabilidad del informe 6.5.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Seccion, Servicio
from apps.expediente.tests.factories import crear_profesional
from apps.farmacia import services
from apps.farmacia.models import Lote, Medicamento, MovimientoInventario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    seccion, _ = Seccion.objects.get_or_create(codigo="salud", defaults={"nombre": "Salud"})
    farmacia, _ = Servicio.objects.get_or_create(
        codigo="farmacia", defaults={"nombre": "Farmacia", "seccion": seccion}
    )
    quimico, perfil = crear_profesional("quimico_inv", farmacia, seccion)
    quimico.set_password(CLAVE)
    quimico.save()
    medicamento = Medicamento.objects.create(
        codigo="MED-001",
        dci="Paracetamol",
        concentracion="500 mg",
        unidad_medida="tableta",
        stock_minimo=50,
    )
    return {"quimico": quimico, "perfil": perfil, "med": medicamento}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


def _fecha(dias):
    return timezone.localdate() + timedelta(days=dias)


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_ajustar_deja_movimiento_con_su_motivo(escenario):
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["perfil"]
    )
    services.ajustar_lote(
        lote, -3, "Conteo físico del 3 de septiembre", usuario=escenario["perfil"]
    )
    lote.refresh_from_db()
    assert lote.cantidad_actual == 97
    movimiento = MovimientoInventario.objects.filter(
        lote=lote, tipo=MovimientoInventario.Tipo.AJUSTE_MENOS
    ).get()
    assert movimiento.cantidad == -3
    assert movimiento.saldo_resultante == 97
    assert "Conteo físico" in movimiento.referencia_doc


@pytest.mark.django_db
def test_un_ajuste_positivo_usa_el_otro_tipo(escenario):
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 10, _fecha(365), usuario=escenario["perfil"]
    )
    services.ajustar_lote(lote, 5, "Aparecieron en bodega", usuario=escenario["perfil"])
    assert MovimientoInventario.objects.filter(
        lote=lote, tipo=MovimientoInventario.Tipo.AJUSTE_MAS
    ).exists()


@pytest.mark.django_db
def test_el_ajuste_exige_motivo_escrito(escenario):
    """Un ajuste sin causa escrita es indistinguible de un descuadre."""
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 10, _fecha(365), usuario=escenario["perfil"]
    )
    with pytest.raises(ValidationError, match="motivo escrito"):
        services.ajustar_lote(lote, -1, "   ", usuario=escenario["perfil"])
    lote.refresh_from_db()
    assert lote.cantidad_actual == 10


@pytest.mark.django_db
def test_el_ajuste_no_deja_el_saldo_negativo(escenario):
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 10, _fecha(365), usuario=escenario["perfil"]
    )
    with pytest.raises(ValidationError, match="no puede ser negativo"):
        services.ajustar_lote(lote, -11, "Robo", usuario=escenario["perfil"])
    lote.refresh_from_db()
    assert lote.cantidad_actual == 10


@pytest.mark.django_db
def test_el_saldo_del_lote_cuadra_con_su_bitacora(escenario):
    """
    La garantía de la trazabilidad: el saldo siempre puede reconstruirse
    sumando los movimientos. Si un ingreso o un ajuste escribiera el saldo sin
    dejar movimiento, esta suma dejaría de cuadrar.
    """
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 100, _fecha(365), usuario=escenario["perfil"]
    )
    services.ingresar_lote(escenario["med"], "L-001", 50, _fecha(365), usuario=escenario["perfil"])
    services.ajustar_lote(lote, -7, "Conteo físico", usuario=escenario["perfil"])
    lote.refresh_from_db()
    suma = sum(m.cantidad for m in lote.movimientos.all())
    assert suma == lote.cantidad_actual == 143


# ------------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_ingresar_un_lote_desde_la_pantalla(escenario):
    cliente = _cliente(escenario["quimico"])
    respuesta = cliente.post(
        reverse("farmacia:inventario"),
        {
            "accion": "ingresar",
            "medicamento": escenario["med"].pk,
            "numero_lote": "L-2026-01",
            "cantidad": "200",
            "fecha_caducidad": _fecha(400).isoformat(),
            "proveedor": "Farmayala",
            "referencia_doc": "Factura 001-234",
        },
        follow=True,
    )
    assert respuesta.status_code == 200
    lote = Lote.objects.get(numero_lote="L-2026-01")
    assert lote.cantidad_actual == 200
    assert lote.proveedor == "Farmayala"
    assert lote.movimientos.get().referencia_doc == "Factura 001-234"


@pytest.mark.django_db
def test_la_pantalla_rechaza_un_lote_ya_caducado(escenario):
    cliente = _cliente(escenario["quimico"])
    respuesta = cliente.post(
        reverse("farmacia:inventario"),
        {
            "accion": "ingresar",
            "medicamento": escenario["med"].pk,
            "numero_lote": "L-VIEJO",
            "cantidad": "10",
            "fecha_caducidad": _fecha(-1).isoformat(),
        },
        follow=True,
    )
    assert "caducado" in respuesta.content.decode()
    assert not Lote.objects.filter(numero_lote="L-VIEJO").exists()


@pytest.mark.django_db
def test_una_cantidad_que_no_es_numero_no_revienta(escenario):
    cliente = _cliente(escenario["quimico"])
    respuesta = cliente.post(
        reverse("farmacia:inventario"),
        {
            "accion": "ingresar",
            "medicamento": escenario["med"].pk,
            "numero_lote": "L-XX",
            "cantidad": "muchas",
            "fecha_caducidad": _fecha(365).isoformat(),
        },
        follow=True,
    )
    assert respuesta.status_code == 200
    assert "número entero" in respuesta.content.decode()


@pytest.mark.django_db
def test_ajustar_desde_la_pantalla(escenario):
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 40, _fecha(365), usuario=escenario["perfil"]
    )
    cliente = _cliente(escenario["quimico"])
    cliente.post(
        reverse("farmacia:inventario"),
        {"accion": "ajustar", "lote": lote.pk, "diferencia": "-4", "motivo": "Conteo físico"},
        follow=True,
    )
    lote.refresh_from_db()
    assert lote.cantidad_actual == 36


@pytest.mark.django_db
def test_dar_de_baja_caducados_desde_la_pantalla(escenario):
    lote = services.ingresar_lote(
        escenario["med"], "L-001", 25, _fecha(1), usuario=escenario["perfil"]
    )
    # Se caduca por el paso del tiempo, no ingresando un lote ya vencido:
    # `ingresar_lote` lo impide, y con razón.
    Lote.objects.filter(pk=lote.pk).update(fecha_caducidad=_fecha(-1))
    cliente = _cliente(escenario["quimico"])
    respuesta = cliente.post(
        reverse("farmacia:inventario"), {"accion": "baja_caducados"}, follow=True
    )
    assert "25 unidades caducadas" in respuesta.content.decode()
    lote.refresh_from_db()
    assert lote.cantidad_actual == 0
    assert lote.movimientos.filter(tipo=MovimientoInventario.Tipo.BAJA).exists()
