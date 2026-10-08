"""Pruebas de solicitud de exámenes de laboratorio."""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import CIE10
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.laboratorio import services
from apps.laboratorio.models import Examen, OrdenLaboratorio
from apps.medicina import services as med_services


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567894")
    CIE10.objects.get_or_create(codigo="J00", defaults={"descripcion": "Resfriado"})
    hemograma = Examen.objects.create(
        codigo="LAB-001", nombre="Biometría hemática", perfil="Hematología"
    )
    glucosa = Examen.objects.create(
        codigo="LAB-002", nombre="Glucosa basal", perfil="Química sanguínea"
    )
    hc = med_services.crear_atencion_medicina(
        expediente=exp,
        profesional=medico,
        motivo="Control",
    )
    return {
        "est": est,
        "medico": medico,
        "exp": exp,
        "hemograma": hemograma,
        "glucosa": glucosa,
        "hc": hc,
    }


@pytest.mark.django_db
def test_crear_orden_desde_medicina(escenario):
    orden = services.crear_orden(
        escenario["hc"].atencion,
        [escenario["hemograma"].id, escenario["glucosa"].id],
        diagnostico_presuntivo="Síndrome febril",
    )
    assert orden.estado == OrdenLaboratorio.Estado.CREADA
    assert orden.examenes.count() == 2
    assert services.ordenes_pendientes().count() == 1


@pytest.mark.django_db
def test_servicio_no_autorizado_rechazado(escenario):
    """Psicología no puede solicitar exámenes (regla del informe 5.2)."""
    _, psicologo = crear_profesional(
        "psi", escenario["est"]["psicologia"], escenario["est"]["psico"]
    )
    atencion = Atencion.objects.create(
        expediente=escenario["exp"],
        servicio=escenario["est"]["psicologia"],
        profesional=psicologo,
        fecha_hora=timezone.now(),
    )
    with pytest.raises(ValidationError, match="no puede solicitar exámenes"):
        services.crear_orden(atencion, [escenario["hemograma"].id])


@pytest.mark.django_db
def test_orden_sin_examenes_rechazada(escenario):
    with pytest.raises(ValidationError, match="al menos un examen"):
        services.crear_orden(escenario["hc"].atencion, [])


@pytest.mark.django_db
def test_no_solicitar_sobre_atencion_firmada(escenario):
    atencion = escenario["hc"].atencion
    atencion.estado = Atencion.Estado.FIRMADA
    atencion.save()
    with pytest.raises(ValidationError, match="firmada"):
        services.crear_orden(atencion, [escenario["hemograma"].id])


@pytest.mark.django_db
def test_un_rango_de_referencia_invertido_se_rechaza(escenario):
    """
    Invertirlo no da error visible: hace que ningún resultado caiga dentro de la
    referencia, así que todos salen marcados alto o bajo y la lectura clínica
    queda falseada en silencio.
    """
    from django.db import IntegrityError, transaction

    from apps.laboratorio.models import Examen, ParametroExamen

    examen = Examen.objects.create(codigo="EX-RANGO", nombre="Prueba")
    with pytest.raises(IntegrityError), transaction.atomic():
        ParametroExamen.objects.create(examen=examen, nombre="Hemoglobina", ref_min=18, ref_max=12)


@pytest.mark.django_db
def test_un_rango_abierto_por_un_lado_sigue_valiendo(escenario):
    """Muchos parámetros solo tienen tope superior o inferior."""
    from apps.laboratorio.models import Examen, ParametroExamen

    examen = Examen.objects.create(codigo="EX-ABIERTO", nombre="Prueba")
    p = ParametroExamen.objects.create(examen=examen, nombre="Glucosa", ref_max=100)
    assert p.pk is not None
