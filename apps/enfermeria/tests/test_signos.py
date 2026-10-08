"""Pruebas de SignosVitales y su reutilización desde Medicina."""

from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.enfermeria.models import SignosVitales
from apps.enfermeria.services import signos_del_dia, ultimo_triaje
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    _, enfermera = crear_profesional("enfermera", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567894")
    return {"est": est, "enfermera": enfermera, "exp": exp}


@pytest.mark.django_db
def test_signos_calcula_imc_automaticamente(escenario):
    sv = SignosVitales.objects.create(
        expediente=escenario["exp"],
        peso=Decimal("70"),
        talla=Decimal("1.70"),
        responsable=escenario["enfermera"],
    )
    assert sv.imc == Decimal("24.2")


@pytest.mark.django_db
def test_signos_sin_peso_no_calcula_imc(escenario):
    sv = SignosVitales.objects.create(
        expediente=escenario["exp"],
        temperatura=Decimal("37.5"),
        fc=88,
        responsable=escenario["enfermera"],
    )
    assert sv.imc is None


@pytest.mark.django_db
def test_signos_del_dia_solo_los_de_hoy(escenario):
    with freeze_time("2026-01-05 14:00:00"):
        SignosVitales.objects.create(
            expediente=escenario["exp"],
            temperatura=Decimal("36.5"),
            responsable=escenario["enfermera"],
        )
    with freeze_time("2026-01-06 10:00:00"):
        SignosVitales.objects.create(
            expediente=escenario["exp"],
            temperatura=Decimal("37.0"),
            responsable=escenario["enfermera"],
        )
        SignosVitales.objects.create(
            expediente=escenario["exp"],
            temperatura=Decimal("37.2"),
            responsable=escenario["enfermera"],
        )
        hoy = signos_del_dia(escenario["exp"])
        assert hoy.count() == 2


@pytest.mark.django_db
def test_ultimo_triaje_reciente(escenario):
    """El último triaje dentro de las últimas 12h se recupera para Medicina."""
    with freeze_time("2026-01-06 09:00:00"):
        SignosVitales.objects.create(
            expediente=escenario["exp"],
            temperatura=Decimal("37.0"),
            fc=85,
            responsable=escenario["enfermera"],
        )
    with freeze_time("2026-01-06 10:30:00"):
        triaje = ultimo_triaje(escenario["exp"])
        assert triaje is not None
        assert triaje.temperatura == Decimal("37.0")


@pytest.mark.django_db
def test_ultimo_triaje_expirado_devuelve_none(escenario):
    """Un triaje de hace 20h ya no cuenta."""
    with freeze_time("2026-01-05 08:00:00"):
        SignosVitales.objects.create(
            expediente=escenario["exp"],
            temperatura=Decimal("36.5"),
            responsable=escenario["enfermera"],
        )
    with freeze_time("2026-01-06 10:00:00"):
        assert ultimo_triaje(escenario["exp"]) is None


@pytest.mark.django_db
def test_el_imc_se_calcula_aunque_lleguen_cadenas(escenario):
    """
    Regresión: `save()` comparaba `self.talla > 0` sin convertir el tipo.

    `self.talla` es lo que se asignó, no lo que el campo convertirá al guardar:
    al crear con `talla="1.65"` —desde el shell, el admin o una carga de datos—
    seguía siendo una cadena, y comparar cadena con entero reventaba con
    TypeError. La vista de triaje se salvaba porque convierte antes con
    `_dec()`; ningún otro camino lo hacía.
    """
    sv = SignosVitales.objects.create(
        expediente=escenario["exp"],
        peso="62.5",
        talla="1.65",
        responsable=escenario["enfermera"],
    )
    assert sv.imc == Decimal("23.0")


@pytest.mark.django_db
def test_sin_talla_se_registra_la_toma_sin_imc(escenario):
    """Falta un dato para el IMC, no la toma entera: se guarda lo demás."""
    sv = SignosVitales.objects.create(
        expediente=escenario["exp"],
        peso="62.5",
        talla=None,
        fc=72,
        responsable=escenario["enfermera"],
    )
    assert sv.imc is None
    assert sv.fc == 72


@pytest.mark.django_db
def test_una_talla_ilegible_se_rechaza_no_se_guarda_a_medias(escenario):
    """
    Una talla que no es un número no entra en silencio: el campo la rechaza.

    Importa que sea así y no un `imc = None` discreto, porque un peso guardado
    junto a una talla basura daría una toma incompleta sin que nadie lo note.
    """
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        SignosVitales.objects.create(
            expediente=escenario["exp"],
            peso="62.5",
            talla="no aplica",
            responsable=escenario["enfermera"],
        )
