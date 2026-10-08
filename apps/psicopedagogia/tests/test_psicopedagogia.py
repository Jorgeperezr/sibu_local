"""Pruebas de la ficha psicopedagógica y la medición de impacto académico."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import PeriodoAcademico, Servicio
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.psicopedagogia import services


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    pp, _ = Servicio.objects.get_or_create(
        codigo="psicopedagogia", defaults={"nombre": "Psicopedagogía", "seccion": est["salud"]}
    )
    _, profesional = crear_profesional("psicopedagogo", pp, pp.seccion)
    exp = crear_expediente(cedula="1104567894")
    PeriodoAcademico.objects.get_or_create(
        codigo="2026-1",
        defaults={
            "nombre": "Periodo 2026-1",
            "fecha_inicio": date(2026, 3, 1),
            "fecha_fin": date(2026, 7, 31),
            "vigente": True,
        },
    )
    PeriodoAcademico.objects.get_or_create(
        codigo="2026-2",
        defaults={
            "nombre": "Periodo 2026-2",
            "fecha_inicio": date(2026, 9, 1),
            "fecha_fin": date(2027, 1, 31),
            "vigente": False,
        },
    )
    return {"est": est, "pp": pp, "profesional": profesional, "exp": exp}


@pytest.mark.django_db
def test_crear_ficha(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"],
        profesional=escenario["profesional"],
        motivo="Bajo rendimiento",
    )
    assert ficha.atencion.servicio.codigo == "psicopedagogia"
    assert ficha.motivo == "Bajo rendimiento"


@pytest.mark.django_db
def test_periodo_inexistente_rechazado(escenario):
    ficha = services.crear_ficha(expediente=escenario["exp"], profesional=escenario["profesional"])
    with pytest.raises(ValidationError, match="no existe"):
        services.registrar_seguimiento(ficha, "2099-9", promedio_antes=5)


@pytest.mark.django_db
def test_promedio_fuera_de_rango(escenario):
    ficha = services.crear_ficha(expediente=escenario["exp"], profesional=escenario["profesional"])
    with pytest.raises(ValidationError, match="entre 0 y 10"):
        services.registrar_seguimiento(ficha, "2026-1", promedio_antes=15)


@pytest.mark.django_db
def test_no_duplica_periodo(escenario):
    ficha = services.crear_ficha(expediente=escenario["exp"], profesional=escenario["profesional"])
    services.registrar_seguimiento(ficha, "2026-1", promedio_antes=Decimal("5.0"))
    services.registrar_seguimiento(ficha, "2026-1", promedio_antes=Decimal("6.0"))
    assert ficha.seguimientos.count() == 1
    assert ficha.seguimientos.first().promedio_antes == Decimal("6.0")


@pytest.mark.django_db
def test_impacto_mide_variacion(escenario):
    ficha = services.crear_ficha(expediente=escenario["exp"], profesional=escenario["profesional"])
    services.registrar_seguimiento(
        ficha, "2026-1", promedio_antes=Decimal("5.0"), promedio_despues=Decimal("7.0")
    )
    services.registrar_seguimiento(
        ficha, "2026-2", promedio_antes=Decimal("6.0"), promedio_despues=Decimal("8.0")
    )
    r = services.impacto(ficha)
    assert r["comparables"] == 2
    assert r["variacion_promedio"] == Decimal("2.00")
    assert r["mejoro"] is True


@pytest.mark.django_db
def test_impacto_ignora_incompletos(escenario):
    """Un seguimiento sin promedio posterior no es comparable y no debe falsear."""
    ficha = services.crear_ficha(expediente=escenario["exp"], profesional=escenario["profesional"])
    services.registrar_seguimiento(
        ficha, "2026-1", promedio_antes=Decimal("5.0"), promedio_despues=Decimal("7.0")
    )
    services.registrar_seguimiento(ficha, "2026-2", promedio_antes=Decimal("6.0"))

    r = services.impacto(ficha)
    assert r["comparables"] == 1
    assert r["incompletos"] == 1
    assert r["variacion_promedio"] == Decimal("2.00")


@pytest.mark.django_db
def test_impacto_sin_datos(escenario):
    ficha = services.crear_ficha(expediente=escenario["exp"], profesional=escenario["profesional"])
    r = services.impacto(ficha)
    assert r["comparables"] == 0
    assert r["variacion_promedio"] is None
    assert r["mejoro"] is None


@pytest.mark.django_db
def test_impacto_detecta_empeoramiento(escenario):
    ficha = services.crear_ficha(expediente=escenario["exp"], profesional=escenario["profesional"])
    services.registrar_seguimiento(
        ficha, "2026-1", promedio_antes=Decimal("7.0"), promedio_despues=Decimal("5.0")
    )
    r = services.impacto(ficha)
    assert r["mejoro"] is False
    assert r["variacion_promedio"] == Decimal("-2.00")
