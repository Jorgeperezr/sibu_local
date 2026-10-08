"""
Las reglas que la base de datos hace cumplir por sí sola.

Estas pruebas no comprueban la lógica de los servicios: comprueban que si
alguien esquiva los servicios —el admin de Django, el shell, una migración de
datos, un `objects.create()` olvidado— la base rechaza el dato imposible.

Cada `assertRaises(IntegrityError)` va en su propio `transaction.atomic()`:
una restricción violada aborta la transacción, y sin el bloque anidado el resto
de la prueba se ejecutaría sobre una transacción muerta.
"""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.citas.models import Agenda, BloqueoAgenda
from apps.enfermeria.models import SignosVitales
from apps.expediente.models import Expediente
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.farmacia.models import Lote, Medicamento


@pytest.fixture
def base(db):
    est = crear_estructura()
    _, prof = crear_profesional("integridad", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567894")
    med = Medicamento.objects.create(codigo="MED-1", dci="Paracetamol", stock_minimo=10)
    return {"est": est, "prof": prof, "exp": exp, "med": med}


# ---------------------------------------------------------------- inventario


@pytest.mark.django_db
def test_un_lote_no_puede_quedar_en_negativo(base):
    """Stock negativo es stock que no existe."""
    lote = Lote.objects.create(
        medicamento=base["med"],
        numero_lote="L1",
        fecha_caducidad=date(2030, 1, 1),
        cantidad_actual=5,
    )
    lote.cantidad_actual = -1
    with pytest.raises(IntegrityError), transaction.atomic():
        lote.save()


@pytest.mark.django_db
def test_no_se_repite_el_numero_de_lote_del_mismo_medicamento(base):
    """
    `ingresar_lote` hace get_or_create sobre esta pareja: sin la restricción,
    dos ingresos simultáneos parten el stock en dos filas gemelas.
    """
    Lote.objects.create(medicamento=base["med"], numero_lote="L1", fecha_caducidad=date(2030, 1, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        Lote.objects.create(
            medicamento=base["med"], numero_lote="L1", fecha_caducidad=date(2031, 1, 1)
        )


@pytest.mark.django_db
def test_el_mismo_numero_de_lote_si_vale_para_otro_medicamento(base):
    """La restricción es por medicamento: dos laboratorios repiten numeración."""
    otro = Medicamento.objects.create(codigo="MED-2", dci="Ibuprofeno")
    Lote.objects.create(medicamento=base["med"], numero_lote="L1", fecha_caducidad=date(2030, 1, 1))
    Lote.objects.create(medicamento=otro, numero_lote="L1", fecha_caducidad=date(2030, 1, 1))
    assert Lote.objects.filter(numero_lote="L1").count() == 2


@pytest.mark.django_db
def test_el_stock_minimo_no_puede_superar_al_maximo(base):
    with pytest.raises(IntegrityError), transaction.atomic():
        Medicamento.objects.create(
            codigo="MED-3", dci="Amoxicilina", stock_minimo=100, stock_maximo=10
        )


@pytest.mark.django_db
def test_maximo_cero_significa_sin_maximo(base):
    """El valor por defecto (0) no debe leerse como un máximo real de cero."""
    med = Medicamento.objects.create(codigo="MED-4", dci="Loratadina", stock_minimo=50)
    assert med.stock_maximo == 0


# ------------------------------------------------------------------- agenda


@pytest.mark.django_db
def test_una_agenda_no_puede_terminar_antes_de_empezar(base):
    """`clean()` ya lo decía, pero solo lo ejecutan los formularios."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Agenda.objects.create(
            profesional=base["prof"],
            servicio=base["est"]["medicina"],
            dia_semana=0,
            hora_inicio=time(16, 0),
            hora_fin=time(8, 0),
        )


@pytest.mark.django_db
def test_un_bloqueo_no_puede_terminar_antes_de_empezar(base):
    ahora = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        BloqueoAgenda.objects.create(
            profesional=base["prof"],
            fecha_inicio=ahora,
            fecha_fin=ahora - timedelta(hours=2),
            motivo="Invertido",
        )


# ------------------------------------------------------------- signos vitales


@pytest.mark.django_db
def test_la_temperatura_fuera_de_rango_se_rechaza(base):
    """36.6 tecleado como 366: el error de digitación clásico del triaje."""
    with pytest.raises(IntegrityError), transaction.atomic():
        SignosVitales.objects.create(
            expediente=base["exp"], temperatura=Decimal("366"), responsable=base["prof"]
        )


@pytest.mark.django_db
def test_la_saturacion_no_pasa_de_100(base):
    with pytest.raises(IntegrityError), transaction.atomic():
        SignosVitales.objects.create(expediente=base["exp"], sat_o2=120, responsable=base["prof"])


@pytest.mark.django_db
def test_la_talla_va_en_metros_no_en_centimetros(base):
    """
    Los centímetros de verdad (175) ya los frena `max_digits=4` del campo. El
    check cubre el hueco que queda: un valor que cabe en el campo pero no en un
    ser humano.
    """
    with pytest.raises(IntegrityError), transaction.atomic():
        SignosVitales.objects.create(
            expediente=base["exp"], talla=Decimal("9.99"), responsable=base["prof"]
        )


@pytest.mark.django_db
def test_la_sistolica_no_puede_ser_menor_que_la_diastolica(base):
    """Invertir las dos cifras de la presión es el error más común."""
    with pytest.raises(IntegrityError), transaction.atomic():
        SignosVitales.objects.create(
            expediente=base["exp"],
            pa_sistolica=80,
            pa_diastolica=120,
            responsable=base["prof"],
        )


@pytest.mark.django_db
def test_un_paciente_grave_sigue_cabiendo_en_los_rangos(base):
    """
    Los rangos son de plausibilidad, no de normalidad clínica: hipotermia
    severa con saturación baja debe poder registrarse.
    """
    sv = SignosVitales.objects.create(
        expediente=base["exp"],
        temperatura=Decimal("28.5"),
        sat_o2=62,
        pa_sistolica=70,
        pa_diastolica=40,
        responsable=base["prof"],
    )
    assert sv.pk is not None


# -------------------------------------------------------------- expediente


@pytest.mark.django_db
def test_la_discapacidad_no_pasa_del_100_por_ciento(base):
    exp = Expediente.objects.get(pk=base["exp"].pk)
    exp.discapacidad_porcentaje = 250
    with pytest.raises(IntegrityError), transaction.atomic():
        exp.save()
