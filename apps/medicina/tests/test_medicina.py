"""Pruebas de creación de HC médica, diagnósticos y cierre."""

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import CIE10
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.medicina import services
from apps.medicina.models import AtencionMedicina, Diagnostico


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567894")
    # Catálogo mínimo CIE-10 para pruebas
    CIE10.objects.get_or_create(
        codigo="J00", defaults={"descripcion": "Rinofaringitis aguda (resfriado común)"}
    )
    CIE10.objects.get_or_create(codigo="R50.9", defaults={"descripcion": "Fiebre, no especificada"})
    return {"est": est, "medico": medico, "exp": exp}


@pytest.mark.django_db
def test_crear_atencion_medicina(escenario):
    hc = services.crear_atencion_medicina(
        expediente=escenario["exp"],
        profesional=escenario["medico"],
        motivo="Tos y fiebre 2 días",
    )
    assert isinstance(hc, AtencionMedicina)
    assert hc.atencion.servicio.codigo == "medicina"
    assert hc.atencion.motivo_consulta == "Tos y fiebre 2 días"
    assert hc.atencion.estado == Atencion.Estado.BORRADOR


@pytest.mark.django_db
def test_agregar_diagnosticos_y_unico_principal(escenario):
    hc = services.crear_atencion_medicina(
        expediente=escenario["exp"],
        profesional=escenario["medico"],
        motivo="x",
    )
    d1 = services.agregar_diagnostico(hc.atencion, "J00", principal=True)
    d2 = services.agregar_diagnostico(hc.atencion, "R50.9", principal=True)  # nuevo principal
    d1.refresh_from_db()
    assert d1.principal is False
    assert d2.principal is True
    assert Diagnostico.objects.filter(atencion=hc.atencion).count() == 2


@pytest.mark.django_db
def test_no_permite_duplicar_diagnostico(escenario):
    hc = services.crear_atencion_medicina(
        expediente=escenario["exp"],
        profesional=escenario["medico"],
        motivo="x",
    )
    services.agregar_diagnostico(hc.atencion, "J00")
    with pytest.raises(ValidationError):
        services.agregar_diagnostico(hc.atencion, "J00")


@pytest.mark.django_db
def test_cerrar_atencion_exige_diagnostico_principal(escenario):
    hc = services.crear_atencion_medicina(
        expediente=escenario["exp"],
        profesional=escenario["medico"],
        motivo="x",
    )
    with pytest.raises(ValidationError, match="al menos un diagnóstico"):
        services.cerrar_atencion(hc.atencion)

    services.agregar_diagnostico(hc.atencion, "J00")  # sin principal
    with pytest.raises(ValidationError, match="principal"):
        services.cerrar_atencion(hc.atencion)

    services.agregar_diagnostico(hc.atencion, "R50.9", principal=True)
    services.cerrar_atencion(hc.atencion)
    hc.atencion.refresh_from_db()
    assert hc.atencion.estado == Atencion.Estado.CERRADA


@pytest.mark.django_db
def test_no_modifica_atencion_firmada(escenario):
    hc = services.crear_atencion_medicina(
        expediente=escenario["exp"],
        profesional=escenario["medico"],
        motivo="x",
    )
    hc.atencion.estado = Atencion.Estado.FIRMADA
    hc.atencion.save()
    with pytest.raises(ValidationError, match="firmada"):
        services.agregar_diagnostico(hc.atencion, "J00")
