"""Pruebas de odontograma, CPO-D y procedimientos."""

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import Seccion, Servicio
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import crear_expediente, crear_profesional
from apps.odontologia import services
from apps.odontologia.models import (
    CatalogoProcedimiento,
    EstadoPieza,
    OdontogramaDetalle,
)


@pytest.fixture
def escenario(db):
    salud, _ = Seccion.objects.get_or_create(codigo="salud", defaults={"nombre": "Salud"})
    odonto, _ = Servicio.objects.get_or_create(
        codigo="odontologia", defaults={"nombre": "Odontología", "seccion": salud}
    )
    _, dentista = crear_profesional("dentista", odonto, salud)
    exp = crear_expediente(cedula="1104567894")

    obturacion = CatalogoProcedimiento.objects.create(
        codigo="OD-001",
        nombre="Obturación con resina",
        requiere_pieza=True,
        estado_resultante=EstadoPieza.OBTURADO,
    )
    profilaxis = CatalogoProcedimiento.objects.create(
        codigo="OD-002", nombre="Profilaxis", requiere_pieza=False
    )
    hc = services.crear_atencion_odontologia(expediente=exp, profesional=dentista, motivo="Control")
    return {
        "odonto": odonto,
        "dentista": dentista,
        "exp": exp,
        "hc": hc,
        "obturacion": obturacion,
        "profilaxis": profilaxis,
    }


@pytest.mark.django_db
def test_crear_atencion_odontologia(escenario):
    assert escenario["hc"].atencion.servicio.codigo == "odontologia"
    assert escenario["hc"].atencion.estado == Atencion.Estado.BORRADOR


@pytest.mark.django_db
def test_pieza_fdi_invalida_rechazada(escenario):
    for invalida in ["19", "50", "99", "1", "abc", "86"]:
        with pytest.raises(ValidationError, match="no es válida"):
            services.registrar_estado_pieza(escenario["hc"].atencion, invalida, EstadoPieza.CARIADO)


@pytest.mark.django_db
def test_piezas_fdi_validas_aceptadas(escenario):
    for valida in ["11", "18", "28", "38", "48", "51", "55", "85"]:
        registro = services.registrar_estado_pieza(
            escenario["hc"].atencion, valida, EstadoPieza.SANO
        )
        assert registro.pieza_fdi == valida


@pytest.mark.django_db
def test_estado_invalido_rechazado(escenario):
    with pytest.raises(ValidationError, match="no válido"):
        services.registrar_estado_pieza(escenario["hc"].atencion, "11", "inventado")


@pytest.mark.django_db
def test_odontograma_conserva_historico(escenario):
    """Registrar un estado nuevo no borra el anterior."""
    atencion = escenario["hc"].atencion
    services.registrar_estado_pieza(atencion, "16", EstadoPieza.CARIADO)
    services.registrar_estado_pieza(
        atencion, "16", EstadoPieza.OBTURADO, tipo=OdontogramaDetalle.TipoRegistro.EVOLUCION
    )

    todos = OdontogramaDetalle.objects.filter(atencion=atencion, pieza_fdi="16")
    assert todos.count() == 2  # histórico completo

    vigente = services.odontograma_vigente(escenario["exp"])
    assert vigente["16"].estado_codigo == EstadoPieza.OBTURADO  # el último gana


@pytest.mark.django_db
def test_cpod_cuenta_solo_permanentes(escenario):
    atencion = escenario["hc"].atencion
    services.registrar_estado_pieza(atencion, "11", EstadoPieza.CARIADO)
    services.registrar_estado_pieza(atencion, "12", EstadoPieza.CARIADO)
    services.registrar_estado_pieza(atencion, "21", EstadoPieza.PERDIDO)
    services.registrar_estado_pieza(atencion, "31", EstadoPieza.OBTURADO)
    services.registrar_estado_pieza(atencion, "41", EstadoPieza.SANO)  # no cuenta
    services.registrar_estado_pieza(atencion, "51", EstadoPieza.CARIADO)  # temporal: no cuenta

    indices = services.calcular_indices(escenario["exp"])
    assert indices["cariados"] == 2
    assert indices["perdidos"] == 1
    assert indices["obturados"] == 1
    assert indices["cpod"] == 4
    assert indices["piezas_registradas"] == 6


@pytest.mark.django_db
def test_cpod_usa_estado_vigente_no_historico(escenario):
    """Si una pieza cariada se obtura, cuenta como obturada, no como cariada."""
    atencion = escenario["hc"].atencion
    services.registrar_estado_pieza(atencion, "16", EstadoPieza.CARIADO)
    indices = services.calcular_indices(escenario["exp"])
    assert indices["cariados"] == 1 and indices["obturados"] == 0

    services.registrar_estado_pieza(
        atencion, "16", EstadoPieza.OBTURADO, tipo=OdontogramaDetalle.TipoRegistro.EVOLUCION
    )
    indices = services.calcular_indices(escenario["exp"])
    assert indices["cariados"] == 0
    assert indices["obturados"] == 1
    assert indices["cpod"] == 1  # sigue siendo 1 pieza afectada


@pytest.mark.django_db
def test_procedimiento_actualiza_odontograma(escenario):
    """Una obturación deja la pieza como 'obturado' automáticamente."""
    atencion = escenario["hc"].atencion
    services.registrar_estado_pieza(atencion, "26", EstadoPieza.CARIADO)

    services.ejecutar_procedimiento(
        atencion, "OD-001", ejecutado_por=escenario["dentista"], pieza_fdi="26"
    )

    vigente = services.odontograma_vigente(escenario["exp"])
    assert vigente["26"].estado_codigo == EstadoPieza.OBTURADO
    assert vigente["26"].tipo == OdontogramaDetalle.TipoRegistro.EVOLUCION
    assert "Obturación" in vigente["26"].observacion


@pytest.mark.django_db
def test_procedimiento_sin_pieza_cuando_la_requiere(escenario):
    with pytest.raises(ValidationError, match="requiere indicar la pieza"):
        services.ejecutar_procedimiento(
            escenario["hc"].atencion, "OD-001", ejecutado_por=escenario["dentista"]
        )


@pytest.mark.django_db
def test_procedimiento_boca_completa_no_requiere_pieza(escenario):
    proc = services.ejecutar_procedimiento(
        escenario["hc"].atencion, "OD-002", ejecutado_por=escenario["dentista"]
    )
    assert proc.pieza_fdi == ""


@pytest.mark.django_db
def test_odontograma_es_acumulativo_entre_atenciones(escenario):
    """El odontograma es del paciente: la segunda atención ve lo de la primera."""
    services.registrar_estado_pieza(escenario["hc"].atencion, "16", EstadoPieza.CARIADO)

    hc2 = services.crear_atencion_odontologia(
        expediente=escenario["exp"], profesional=escenario["dentista"], motivo="Segunda visita"
    )
    vigente = services.odontograma_vigente(escenario["exp"])
    assert "16" in vigente  # ve el registro de la atención anterior

    services.ejecutar_procedimiento(
        hc2.atencion, "OD-001", ejecutado_por=escenario["dentista"], pieza_fdi="16"
    )
    vigente = services.odontograma_vigente(escenario["exp"])
    assert vigente["16"].estado_codigo == EstadoPieza.OBTURADO


@pytest.mark.django_db
def test_cerrar_exige_odontograma(escenario):
    with pytest.raises(ValidationError, match="odontograma"):
        services.cerrar_atencion(escenario["hc"].atencion)

    services.registrar_estado_pieza(escenario["hc"].atencion, "11", EstadoPieza.CARIADO)
    services.cerrar_atencion(escenario["hc"].atencion)

    escenario["hc"].refresh_from_db()
    assert escenario["hc"].atencion.estado == Atencion.Estado.CERRADA
    assert escenario["hc"].indices["cpod"] == 1  # índices congelados al cierre


@pytest.mark.django_db
def test_no_modificar_atencion_firmada(escenario):
    atencion = escenario["hc"].atencion
    atencion.estado = Atencion.Estado.FIRMADA
    atencion.save()
    with pytest.raises(ValidationError, match="firmada"):
        services.registrar_estado_pieza(atencion, "11", EstadoPieza.CARIADO)
    with pytest.raises(ValidationError, match="firmada"):
        services.ejecutar_procedimiento(
            atencion, "OD-001", ejecutado_por=escenario["dentista"], pieza_fdi="11"
        )
