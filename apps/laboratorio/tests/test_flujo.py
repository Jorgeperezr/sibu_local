"""Pruebas del flujo completo de laboratorio: muestra → resultado → validación → publicación."""

from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import ValidationError

from apps.core.models import CIE10
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.laboratorio import services
from apps.laboratorio.models import (
    Examen,
    OrdenLaboratorio,
    ParametroExamen,
    ResultadoParametro,
)
from apps.medicina import services as med_services


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    _, tecnico = crear_profesional("tecnico", est["medicina"], est["salud"])
    _, responsable = crear_profesional("responsable", est["medicina"], est["salud"])

    exp = crear_expediente(cedula="1104567894")
    exp.persona.sexo = "M"
    exp.persona.fecha_nacimiento = date(2000, 5, 15)
    exp.persona.correo_institucional = "estudiante@unl.edu.ec"
    exp.persona.save()

    CIE10.objects.get_or_create(codigo="J00", defaults={"descripcion": "Resfriado"})

    biometria = Examen.objects.create(codigo="LAB-001", nombre="Biometría hemática")
    hemoglobina = ParametroExamen.objects.create(
        examen=biometria,
        nombre="Hemoglobina",
        unidad="g/dL",
        sexo=ParametroExamen.Sexo.MASCULINO,
        ref_min=Decimal("13.0"),
        ref_max=Decimal("17.0"),
        critico_min=Decimal("7.0"),
        orden=1,
    )
    leucocitos = ParametroExamen.objects.create(
        examen=biometria,
        nombre="Leucocitos",
        unidad="10³/µL",
        ref_min=Decimal("4.5"),
        ref_max=Decimal("11.0"),
        orden=2,
    )

    hc = med_services.crear_atencion_medicina(expediente=exp, profesional=medico, motivo="Control")
    orden = services.crear_orden(hc.atencion, [biometria.id])
    return {
        "est": est,
        "medico": medico,
        "tecnico": tecnico,
        "responsable": responsable,
        "exp": exp,
        "biometria": biometria,
        "hemoglobina": hemoglobina,
        "leucocitos": leucocitos,
        "orden": orden,
        "orden_examen": orden.examenes.first(),
    }


@pytest.mark.django_db
def test_tomar_muestra_genera_codigo_barras(escenario):
    orden = services.tomar_muestra(
        escenario["orden"], escenario["tecnico"], tipo_muestra="Sangre venosa"
    )
    assert orden.estado == OrdenLaboratorio.Estado.MUESTRA_TOMADA
    assert orden.codigo_barras
    assert orden.fecha_toma_muestra is not None


@pytest.mark.django_db
def test_rechazar_muestra_exige_motivo(escenario):
    with pytest.raises(ValidationError, match="motivo"):
        services.rechazar_muestra(escenario["orden"], "")
    orden = services.rechazar_muestra(escenario["orden"], "Muestra hemolizada")
    assert orden.estado == OrdenLaboratorio.Estado.RECHAZADA


@pytest.mark.django_db
def test_no_registrar_resultado_sin_muestra(escenario):
    with pytest.raises(ValidationError, match="toma de muestra"):
        services.registrar_resultado(
            escenario["orden_examen"],
            escenario["hemoglobina"],
            "14.5",
            registrado_por=escenario["tecnico"],
        )


@pytest.mark.django_db
def test_marcador_normal_alto_bajo_critico(escenario):
    services.tomar_muestra(escenario["orden"], escenario["tecnico"])
    oe, hb, tec = escenario["orden_examen"], escenario["hemoglobina"], escenario["tecnico"]

    r = services.registrar_resultado(oe, hb, "14.5", registrado_por=tec)
    assert r.marcador == ResultadoParametro.Marcador.NORMAL

    r = services.registrar_resultado(oe, hb, "18.0", registrado_por=tec)
    assert r.marcador == ResultadoParametro.Marcador.ALTO

    r = services.registrar_resultado(oe, hb, "11.0", registrado_por=tec)
    assert r.marcador == ResultadoParametro.Marcador.BAJO

    r = services.registrar_resultado(oe, hb, "6.5", registrado_por=tec)
    assert r.marcador == ResultadoParametro.Marcador.CRITICO


@pytest.mark.django_db
def test_parametro_ajeno_al_examen_rechazado(escenario):
    services.tomar_muestra(escenario["orden"], escenario["tecnico"])
    otro_examen = Examen.objects.create(codigo="LAB-002", nombre="Glucosa")
    glucosa = ParametroExamen.objects.create(examen=otro_examen, nombre="Glucosa basal")
    with pytest.raises(ValidationError, match="no pertenece"):
        services.registrar_resultado(
            escenario["orden_examen"], glucosa, "90", registrado_por=escenario["tecnico"]
        )


@pytest.mark.django_db
def test_segregacion_de_funciones_en_validacion(escenario):
    """Quien registra los resultados no puede validarlos."""
    services.tomar_muestra(escenario["orden"], escenario["tecnico"])
    services.registrar_resultado(
        escenario["orden_examen"],
        escenario["hemoglobina"],
        "14.5",
        registrado_por=escenario["tecnico"],
    )
    services.marcar_resultado_completo(escenario["orden"])

    with pytest.raises(ValidationError, match="segregación de funciones"):
        services.validar_orden(escenario["orden"], escenario["tecnico"])

    orden = services.validar_orden(escenario["orden"], escenario["responsable"])
    assert orden.estado == OrdenLaboratorio.Estado.VALIDADO
    assert orden.validado_por == escenario["responsable"]


@pytest.mark.django_db
def test_publicar_envia_correo_al_paciente(escenario):
    services.tomar_muestra(escenario["orden"], escenario["tecnico"])
    services.registrar_resultado(
        escenario["orden_examen"],
        escenario["hemoglobina"],
        "14.5",
        registrado_por=escenario["tecnico"],
    )
    services.marcar_resultado_completo(escenario["orden"])
    services.validar_orden(escenario["orden"], escenario["responsable"])

    orden = services.publicar_orden(escenario["orden"])

    assert orden.estado == OrdenLaboratorio.Estado.PUBLICADO
    assert orden.enviado_correo_paciente is True
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["estudiante@unl.edu.ec"]
    assert "Hemoglobina" in mail.outbox[0].body
    assert "no constituye un diagnóstico" in mail.outbox[0].body


@pytest.mark.django_db
def test_sin_correo_institucional_no_envia_pero_deja_constancia(escenario):
    from apps.notificaciones.models import Notificacion

    escenario["exp"].persona.correo_institucional = ""
    escenario["exp"].persona.save()

    services.tomar_muestra(escenario["orden"], escenario["tecnico"])
    services.registrar_resultado(
        escenario["orden_examen"],
        escenario["hemoglobina"],
        "14.5",
        registrado_por=escenario["tecnico"],
    )
    services.marcar_resultado_completo(escenario["orden"])
    services.validar_orden(escenario["orden"], escenario["responsable"])
    orden = services.publicar_orden(escenario["orden"])

    assert orden.enviado_correo_paciente is False
    assert len(mail.outbox) == 0
    assert Notificacion.objects.filter(tipo="resultado_sin_correo").exists()


@pytest.mark.django_db
def test_valor_critico_genera_alerta_al_solicitante(escenario):
    from apps.notificaciones.models import Notificacion

    services.tomar_muestra(escenario["orden"], escenario["tecnico"])
    services.registrar_resultado(
        escenario["orden_examen"],
        escenario["hemoglobina"],
        "6.0",
        registrado_por=escenario["tecnico"],
    )
    services.marcar_resultado_completo(escenario["orden"])
    services.validar_orden(escenario["orden"], escenario["responsable"])
    services.publicar_orden(escenario["orden"])

    alerta = Notificacion.objects.filter(tipo="resultado_critico").first()
    assert alerta is not None
    assert "6.0" in alerta.mensaje
    assert escenario["orden"].tiene_criticos is True


@pytest.mark.django_db
def test_no_publicar_sin_validar(escenario):
    services.tomar_muestra(escenario["orden"], escenario["tecnico"])
    services.registrar_resultado(
        escenario["orden_examen"],
        escenario["hemoglobina"],
        "14.5",
        registrado_por=escenario["tecnico"],
    )
    with pytest.raises(ValidationError, match="validadas"):
        services.publicar_orden(escenario["orden"])


@pytest.mark.django_db
def test_no_registrar_sobre_orden_validada(escenario):
    services.tomar_muestra(escenario["orden"], escenario["tecnico"])
    services.registrar_resultado(
        escenario["orden_examen"],
        escenario["hemoglobina"],
        "14.5",
        registrado_por=escenario["tecnico"],
    )
    services.marcar_resultado_completo(escenario["orden"])
    services.validar_orden(escenario["orden"], escenario["responsable"])
    with pytest.raises(ValidationError, match="No se pueden registrar"):
        services.registrar_resultado(
            escenario["orden_examen"],
            escenario["leucocitos"],
            "7.0",
            registrado_por=escenario["tecnico"],
        )


@pytest.mark.django_db
def test_rango_por_sexo_se_aplica(escenario):
    """El rango masculino no aplica a una paciente femenina."""
    hb_masculino = escenario["hemoglobina"]
    assert hb_masculino.aplica_a("M", 25) is True
    assert hb_masculino.aplica_a("F", 25) is False


@pytest.mark.django_db
def test_ordenes_pendientes_prioriza_urgentes(escenario):
    from apps.medicina import services as med

    hc2 = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["medico"], motivo="Urgente"
    )
    services.crear_orden(hc2.atencion, [escenario["biometria"].id], prioridad="urgente")
    pendientes = list(services.ordenes_pendientes())
    assert pendientes[0].prioridad == "urgente"
