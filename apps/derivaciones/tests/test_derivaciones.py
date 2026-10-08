"""Pruebas del ciclo de derivaciones y del sello de confidencialidad en el retorno."""

import pytest
from django.core.exceptions import ValidationError
from freezegun import freeze_time

from apps.core.models import Servicio
from apps.derivaciones import services
from apps.derivaciones.models import Derivacion
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    psico, _ = Servicio.objects.get_or_create(
        codigo="psicologia", defaults={"nombre": "Psicología", "seccion": est["salud"]}
    )
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    _, psicologo = crear_profesional("psicologo", psico, psico.seccion)
    exp = crear_expediente(cedula="1104567894")
    atencion_med = crear_atencion(exp, est["medicina"], medico)
    return {
        "est": est,
        "psico": psico,
        "medico": medico,
        "psicologo": psicologo,
        "exp": exp,
        "atencion_med": atencion_med,
    }


@pytest.mark.django_db
def test_derivar_crea_en_estado_enviada(escenario):
    d = services.derivar(
        escenario["atencion_med"], escenario["psico"], motivo="Sospecha de depresión"
    )
    assert d.estado == Derivacion.Estado.ENVIADA
    assert d.servicio_destino == escenario["psico"]


@pytest.mark.django_db
def test_no_derivar_al_mismo_servicio(escenario):
    with pytest.raises(ValidationError, match="mismo servicio"):
        services.derivar(escenario["atencion_med"], escenario["est"]["medicina"], motivo="X")


@pytest.mark.django_db
def test_motivo_obligatorio(escenario):
    with pytest.raises(ValidationError, match="motivo"):
        services.derivar(escenario["atencion_med"], escenario["psico"], motivo="")


@pytest.mark.django_db
def test_no_duplicar_derivacion_abierta(escenario):
    services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Depresión")
    with pytest.raises(ValidationError, match="ya tiene una derivación abierta"):
        services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Otra vez")


@pytest.mark.django_db
def test_ciclo_completo(escenario):
    d = services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Depresión")
    services.aceptar(d)
    assert d.estado == Derivacion.Estado.ACEPTADA
    services.marcar_agendada(d)
    assert d.estado == Derivacion.Estado.AGENDADA

    atencion_psico = crear_atencion(escenario["exp"], escenario["psico"], escenario["psicologo"])
    services.atender(d, atencion_psico)
    assert d.estado == Derivacion.Estado.ATENDIDA
    assert d.atencion_destino == atencion_psico


@pytest.mark.django_db
def test_atender_con_atencion_de_otro_servicio(escenario):
    d = services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Depresión")
    services.aceptar(d)
    otra = crear_atencion(escenario["exp"], escenario["est"]["medicina"], escenario["medico"])
    with pytest.raises(ValidationError, match="pero la derivación es a"):
        services.atender(d, otra)


@pytest.mark.django_db
def test_atender_con_paciente_distinto(escenario):
    d = services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Depresión")
    services.aceptar(d)
    otro_exp = crear_expediente(cedula="1102030408")
    atencion_otro = crear_atencion(otro_exp, escenario["psico"], escenario["psicologo"])
    with pytest.raises(ValidationError, match="otro paciente"):
        services.atender(d, atencion_otro)


@pytest.mark.django_db
def test_retorno_de_psicologia_no_filtra_contenido_clinico(escenario):
    """
    EL HUECO: retorno_texto es legible por quien derivó. Si Psicología escribe
    su evolución ahí, el médico la leería y el sello sería burlable.
    """
    d = services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Depresión")
    services.aceptar(d)
    atencion_psico = crear_atencion(escenario["exp"], escenario["psico"], escenario["psicologo"])
    services.atender(d, atencion_psico)

    services.retornar(
        d,
        "Paciente con ideación suicida activa, plan estructurado, se inicia terapia "
        "cognitivo-conductual y se contacta a la familia.",
    )
    d.refresh_from_db()

    # El contenido clínico NO llega al que derivó.
    assert "ideación suicida" not in d.retorno_texto
    assert "cognitivo-conductual" not in d.retorno_texto
    assert "familia" not in d.retorno_texto
    # Pero sí sabe que fue atendido y a quién contactar.
    assert "atendido" in d.retorno_texto.lower()
    assert "confidencialidad" in d.retorno_texto.lower()
    assert d.estado == Derivacion.Estado.RETORNADA


@pytest.mark.django_db
def test_retorno_de_servicio_normal_si_conserva_el_texto(escenario):
    """Contraste: una derivación a un servicio NO confidencial sí retorna contenido."""
    from apps.expediente.models import Atencion

    enfermeria = escenario["est"].get("enfermeria")
    if enfermeria is None:
        enfermeria, _ = Servicio.objects.get_or_create(
            codigo="enfermeria",
            defaults={"nombre": "Enfermería", "seccion": escenario["est"]["salud"]},
        )
    _, enfermera = crear_profesional("enfermera", enfermeria, escenario["est"]["salud"])

    d = services.derivar(escenario["atencion_med"], enfermeria, motivo="Curación")
    services.aceptar(d)
    atencion_enf = Atencion.objects.create(
        expediente=escenario["exp"],
        servicio=enfermeria,
        profesional=enfermera,
        fecha_hora=escenario["atencion_med"].fecha_hora,
    )
    services.atender(d, atencion_enf)
    services.retornar(d, "Curación realizada, herida sin signos de infección.")
    d.refresh_from_db()

    assert "sin signos de infección" in d.retorno_texto


@pytest.mark.django_db
def test_referencia_externa_bloqueada_desde_psicologia(escenario):
    """El resumen clínico saldría de la Unidad: Psicología no usa este canal."""
    atencion_psico = crear_atencion(escenario["exp"], escenario["psico"], escenario["psicologo"])
    with pytest.raises(ValidationError, match="no emite referencias externas"):
        services.referir_a_externo(atencion_psico, institucion="Hospital X", motivo="Psiquiatría")


@pytest.mark.django_db
def test_referencia_externa_permitida_desde_medicina(escenario):
    ref = services.referir_a_externo(
        escenario["atencion_med"],
        institucion="Hospital Isidro Ayora",
        motivo="Valoración cardiológica",
        especialidad="Cardiología",
    )
    assert ref.institucion_destino == "Hospital Isidro Ayora"


@pytest.mark.django_db
def test_contrarreferencia_unica(escenario):
    ref = services.referir_a_externo(
        escenario["atencion_med"], institucion="Hospital X", motivo="Valoración"
    )
    services.registrar_contrarreferencia(ref, hallazgos="Normal")
    with pytest.raises(ValidationError, match="ya tiene contrarreferencia"):
        services.registrar_contrarreferencia(ref, hallazgos="Otra")


@pytest.mark.django_db
def test_rechazar_exige_motivo(escenario):
    d = services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Depresión")
    with pytest.raises(ValidationError, match="motivo del rechazo"):
        services.rechazar(d, "")
    services.rechazar(d, "Paciente no corresponde al servicio")
    assert d.estado == Derivacion.Estado.RECHAZADA


@pytest.mark.django_db
def test_bandeja_prioriza_urgentes(escenario):
    services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Rutina")
    otro_exp = crear_expediente(cedula="1102030408")
    atencion2 = crear_atencion(otro_exp, escenario["est"]["medicina"], escenario["medico"])
    services.derivar(atencion2, escenario["psico"], motivo="Crisis", prioridad="urgente")

    bandeja = list(services.bandeja_entrada(escenario["psico"]))
    assert bandeja[0].prioridad == "urgente"


@pytest.mark.django_db
def test_trazabilidad_marca_confidenciales(escenario):
    """
    Marcarlas está bien; lo que no bastaba era marcarlas. La marca se conserva
    —la pantalla pinta el candado con ella— pero ahora quien no es de ninguno
    de los dos servicios ni siquiera recibe la fila: ver que existe ya dice que
    la persona es paciente de Psicología. El caso completo está en
    `test_trazabilidad_sello.py`.
    """
    services.derivar(escenario["atencion_med"], escenario["psico"], motivo="Depresión")
    traza = services.trazabilidad(escenario["exp"], escenario["medico"].usuario)
    assert len(traza) == 1
    assert traza[0]["hacia"] == escenario["psico"].nombre
    assert traza[0]["confidencial"] is True


@pytest.mark.django_db
@freeze_time("2026-07-17 00:29:00")  # 19:29 en Loja del día 16 (UTC-5)
def test_contrarreferencia_el_mismo_dia_despues_de_las_19h(escenario):
    """
    Regresión de zona horaria.

    `creado_en` se guarda en UTC. A las 19:29 en Loja ya son las 00:29 UTC del
    día siguiente, así que comparar `creado_en.date()` (UTC) contra
    `timezone.localdate()` (local) rechazaba erróneamente toda contrarreferencia
    registrada entre las 19:00 y la medianoche. Todos los días.
    """
    from django.utils import timezone

    ref = services.referir_a_externo(
        escenario["atencion_med"], institucion="Hospital X", motivo="Valoración"
    )
    # La referencia se emitió hoy en hora local...
    assert timezone.localdate() == timezone.localtime(ref.creado_en).date()
    # ...pero en UTC ya es mañana: ahí estaba el bug.
    assert ref.creado_en.date() != timezone.localdate()

    contra = services.registrar_contrarreferencia(ref, hallazgos="Sin novedad")
    assert contra.fecha_recepcion == timezone.localdate()


@pytest.mark.django_db
@freeze_time("2026-07-16 15:00:00")  # 10:00 en Loja: fuera de la ventana
def test_contrarreferencia_anterior_a_la_referencia_sigue_rechazada(escenario):
    """La validación real debe seguir funcionando: no se relajó, se corrigió."""
    from datetime import timedelta

    from django.utils import timezone

    ref = services.referir_a_externo(
        escenario["atencion_med"], institucion="Hospital X", motivo="Valoración"
    )
    ayer = timezone.localdate() - timedelta(days=1)
    with pytest.raises(ValidationError, match="anterior a la emisión"):
        services.registrar_contrarreferencia(ref, fecha_recepcion=ayer)
