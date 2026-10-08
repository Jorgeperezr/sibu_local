"""
Portal de autogestión.

El portal es superficie pública: las pruebas que importan son las de
aislamiento. Un estudiante no debe alcanzar nada de otro —ni manipulando
IDs— y el portal no debe filtrar contenido clínico.
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from apps.core.models import PeriodoAcademico, Servicio
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.portal import services
from apps.portal.models import VinculacionPortal
from apps.usuarios.models import Rol, Usuario

CEDULA_A = "1100000007"
CEDULA_B = "1700000001"
CLAVE = "clave-larga-12345"


def _estudiante(username):
    return Usuario.objects.create_user(
        username=username, password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )


def _con_correo(exp, correo):
    periodo, _ = PeriodoAcademico.objects.get_or_create(
        codigo="2026-1",
        defaults={
            "nombre": "2026-1",
            "fecha_inicio": date(2026, 3, 1),
            "fecha_fin": date(2026, 7, 31),
            "vigente": True,
        },
    )
    from apps.academico.models import DatoAcademico

    DatoAcademico.objects.create(persona=exp.persona, periodo=periodo, email_institucional=correo)
    return exp


def _vincular(usuario, exp):
    return VinculacionPortal.objects.create(
        usuario=usuario,
        expediente=exp,
        verificado=True,
        correo_destino="x@unl.edu.ec",
        token_hash="x",
        token_expira_en=timezone.now(),
    )


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    exp_a = _con_correo(crear_expediente(cedula=CEDULA_A), "ana@unl.edu.ec")
    exp_b = _con_correo(crear_expediente(cedula=CEDULA_B), "beto@unl.edu.ec")
    ana, beto = _estudiante("ana"), _estudiante("beto")
    return {"est": est, "exp_a": exp_a, "exp_b": exp_b, "ana": ana, "beto": beto}


# --------------------------------------------------------------------------
# Vinculación
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_el_codigo_viaja_al_correo_institucional_no_a_uno_digitado(escenario):
    """
    La defensa central del portal.

    Si el correo lo eligiera quien se registra, cualquiera vincularía el
    expediente de otra persona con su propia casilla. La posesión de la casilla
    institucional ES la prueba de identidad.
    """
    v = services.solicitar_vinculacion(escenario["ana"], CEDULA_A)
    assert v.correo_destino == "ana@unl.edu.ec"
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["ana@unl.edu.ec"]


@pytest.mark.django_db
def test_el_token_no_se_guarda_en_claro(escenario):
    services.solicitar_vinculacion(escenario["ana"], CEDULA_A)
    v = VinculacionPortal.objects.get(usuario=escenario["ana"])
    token_enviado = mail.outbox[0].body.split("Código de confirmación: ")[1].split("\n")[0]
    assert token_enviado not in v.token_hash
    assert v.token_hash == VinculacionPortal.hashear(token_enviado)


@pytest.mark.django_db
def test_confirmar_con_el_token_correcto(escenario):
    services.solicitar_vinculacion(escenario["ana"], CEDULA_A)
    token = mail.outbox[0].body.split("Código de confirmación: ")[1].split("\n")[0]
    v = services.confirmar_vinculacion(escenario["ana"], token)
    assert v.verificado is True
    assert services.expediente_de(escenario["ana"]) == escenario["exp_a"]


@pytest.mark.django_db
def test_token_incorrecto_no_confirma(escenario):
    services.solicitar_vinculacion(escenario["ana"], CEDULA_A)
    with pytest.raises(ValidationError, match="no es correcto"):
        services.confirmar_vinculacion(escenario["ana"], "token-inventado")


@pytest.mark.django_db
def test_token_caducado_no_confirma(escenario):
    services.solicitar_vinculacion(escenario["ana"], CEDULA_A)
    VinculacionPortal.objects.filter(usuario=escenario["ana"]).update(
        token_expira_en=timezone.now() - timedelta(hours=1)
    )
    token = mail.outbox[0].body.split("Código de confirmación: ")[1].split("\n")[0]
    with pytest.raises(ValidationError, match="caducó"):
        services.confirmar_vinculacion(escenario["ana"], token)


@pytest.mark.django_db
def test_un_expediente_no_se_vincula_a_dos_cuentas(escenario):
    """El segundo intento se rechaza Y queda auditado: puede ser un ataque."""
    from apps.auditoria.models import LogAuditoria

    _vincular(escenario["ana"], escenario["exp_a"])
    with pytest.raises(ValidationError, match="ya está vinculado"):
        services.solicitar_vinculacion(escenario["beto"], CEDULA_A)
    log = LogAuditoria.objects.filter(modulo="portal", resultado="rechazado").first()
    assert log is not None
    assert log.usuario == escenario["beto"]


@pytest.mark.django_db
def test_sin_correo_institucional_la_vinculacion_es_presencial(escenario):
    crear_expediente(cedula="1100000015")  # sin dato académico
    carlos = _estudiante("carlos")
    with pytest.raises(ValidationError, match="presencialmente"):
        services.solicitar_vinculacion(carlos, "1100000015")


@pytest.mark.django_db
def test_un_profesional_no_usa_el_portal(escenario):
    u, _ = crear_profesional("medico", escenario["est"]["medicina"], escenario["est"]["salud"])
    with pytest.raises(ValidationError, match="estudiantes"):
        services.solicitar_vinculacion(u, CEDULA_A)


# --------------------------------------------------------------------------
# Aislamiento: lo que hace del portal un portal
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_un_estudiante_no_cancela_la_cita_de_otro(escenario):
    """Manipular el id de la cita en el POST no alcanza recursos ajenos."""
    from apps.citas.models import Cita

    _vincular(escenario["ana"], escenario["exp_a"])
    _vincular(escenario["beto"], escenario["exp_b"])
    _, prof = crear_profesional("med2", escenario["est"]["medicina"], escenario["est"]["salud"])
    cita_de_beto = Cita.objects.create(
        expediente=escenario["exp_b"],
        servicio=escenario["est"]["medicina"],
        profesional=prof,
        fecha_hora=timezone.now() + timedelta(days=2),
    )
    with pytest.raises(ValidationError, match="no existe o no le pertenece"):
        services.cancelar_mi_cita(escenario["exp_a"], cita_de_beto.pk, escenario["ana"])
    cita_de_beto.refresh_from_db()
    assert cita_de_beto.estado != Cita.Estado.CANCELADA


@pytest.mark.django_db
def test_el_mensaje_no_confirma_si_la_cita_ajena_existe(escenario):
    """El mismo error exista o no: no se enumera lo de otros."""
    _vincular(escenario["ana"], escenario["exp_a"])
    with pytest.raises(ValidationError, match="no existe o no le pertenece"):
        services.cancelar_mi_cita(escenario["exp_a"], 99999, escenario["ana"])


@pytest.mark.django_db
def test_el_panel_solo_muestra_lo_propio(escenario):
    from apps.citas.models import Cita

    _vincular(escenario["ana"], escenario["exp_a"])
    _, prof = crear_profesional("med3", escenario["est"]["medicina"], escenario["est"]["salud"])
    Cita.objects.create(
        expediente=escenario["exp_b"],
        servicio=escenario["est"]["medicina"],
        profesional=prof,
        fecha_hora=timezone.now() + timedelta(days=1),
    )
    c = Client()
    c.login(username="ana", password=CLAVE)
    r = c.get("/portal/")
    assert r.status_code == 200
    assert escenario["exp_b"].persona.nombre_completo not in r.content.decode()


@pytest.mark.django_db
def test_el_portal_no_filtra_el_proceso_psicologico(escenario):
    """
    El estudiante sí ve SU cita con psicología (él la agendó), pero el portal
    no expone nada del contenido del proceso: ni motivo, ni riesgo, ni notas.
    """
    from apps.psicologia import services as psi

    psico = Servicio.objects.get(codigo="psicologia")
    _, psicologo = crear_profesional("psico1", psico, psico.seccion)
    ficha = psi.crear_ficha(
        expediente=escenario["exp_a"],
        profesional=psicologo,
        motivo="Ideación suicida con plan estructurado",
    )
    psi.registrar_sesion(ficha, profesional=psicologo, evolucion="Contenido de sesión reservado")
    _vincular(escenario["ana"], escenario["exp_a"])

    c = Client()
    c.login(username="ana", password=CLAVE)
    for url in ("/portal/", "/portal/citas/"):
        cuerpo = c.get(url).content.decode()
        assert "Ideación suicida" not in cuerpo
        assert "Contenido de sesión" not in cuerpo


@pytest.mark.django_db
def test_usuario_final_no_entra_a_las_vistas_de_profesionales(escenario):
    """La cuenta del portal no navega bandejas clínicas ni expedientes."""
    from apps.core.models import Seccion

    seccion, _ = Seccion.objects.get_or_create(codigo="becas", defaults={"nombre": "Becas"})
    Servicio.objects.get_or_create(
        codigo="becas-y-ayudas-economicas",
        defaults={"nombre": "Becas", "seccion": seccion},
    )
    _vincular(escenario["ana"], escenario["exp_a"])
    c = Client()
    c.login(username="ana", password=CLAVE)
    for url in ("/psicologia/", "/becas/", "/talleres/", "/derivaciones/"):
        r = c.get(url)
        assert r.status_code == 403, f"{url} devolvió {r.status_code} a un usuario del portal"


@pytest.mark.django_db
def test_un_profesional_no_navega_el_portal(escenario):
    u, _ = crear_profesional("med4", escenario["est"]["medicina"], escenario["est"]["salud"])
    u.set_password(CLAVE)
    u.save()
    c = Client()
    c.login(username="med4", password=CLAVE)
    assert c.get("/portal/").status_code == 403


# --------------------------------------------------------------------------
# Citas desde el portal
# --------------------------------------------------------------------------


@pytest.fixture
def con_agenda(escenario):
    from apps.citas.models import Agenda

    _, prof = crear_profesional("med5", escenario["est"]["medicina"], escenario["est"]["salud"])
    manana = timezone.localdate() + timedelta(days=1)
    Agenda.objects.create(
        profesional=prof,
        servicio=escenario["est"]["medicina"],
        dia_semana=manana.weekday(),
        hora_inicio="08:00",
        hora_fin="12:00",
        duracion_turno_min=20,
        vigente_desde=timezone.localdate(),
        activa=True,
    )
    return {**escenario, "prof": prof, "manana": manana}


@pytest.mark.django_db
def test_agendar_en_un_turno_libre(con_agenda):
    from apps.citas import services as citas_services
    from apps.citas.models import Cita

    _vincular(con_agenda["ana"], con_agenda["exp_a"])
    turnos = citas_services.turnos_disponibles(
        con_agenda["prof"], con_agenda["est"]["medicina"], con_agenda["manana"]
    )
    assert turnos, "la agenda no generó turnos"
    cita = services.agendar_cita(
        con_agenda["exp_a"],
        servicio=con_agenda["est"]["medicina"],
        profesional=con_agenda["prof"],
        fecha_hora=turnos[0],
        usuario=con_agenda["ana"],
    )
    assert cita.origen == Cita.Origen.AUTOGESTION


@pytest.mark.django_db
def test_el_limite_de_citas_activas_frena_el_abuso(con_agenda):
    from apps.citas import services as citas_services

    _vincular(con_agenda["ana"], con_agenda["exp_a"])
    turnos = citas_services.turnos_disponibles(
        con_agenda["prof"], con_agenda["est"]["medicina"], con_agenda["manana"]
    )
    for turno in turnos[: services.MAX_CITAS_ACTIVAS_PORTAL]:
        services.agendar_cita(
            con_agenda["exp_a"],
            servicio=con_agenda["est"]["medicina"],
            profesional=con_agenda["prof"],
            fecha_hora=turno,
            usuario=con_agenda["ana"],
        )
    with pytest.raises(ValidationError, match="citas activas"):
        services.agendar_cita(
            con_agenda["exp_a"],
            servicio=con_agenda["est"]["medicina"],
            profesional=con_agenda["prof"],
            fecha_hora=turnos[services.MAX_CITAS_ACTIVAS_PORTAL],
            usuario=con_agenda["ana"],
        )


@pytest.mark.django_db
def test_solo_resultados_publicados(escenario):
    """Lo no publicado aún no pasó la validación en dos pasos del laboratorio."""
    from apps.expediente.models import Atencion
    from apps.laboratorio.models import OrdenLaboratorio

    _, prof = crear_profesional("med6", escenario["est"]["medicina"], escenario["est"]["salud"])
    at = Atencion.objects.create(
        expediente=escenario["exp_a"],
        servicio=escenario["est"]["medicina"],
        profesional=prof,
        fecha_hora=timezone.now(),
    )
    OrdenLaboratorio.objects.create(atencion=at, estado=OrdenLaboratorio.Estado.VALIDADO)
    publicada = OrdenLaboratorio.objects.create(
        atencion=at, estado=OrdenLaboratorio.Estado.PUBLICADO, publicado_en=timezone.now()
    )
    _vincular(escenario["ana"], escenario["exp_a"])
    assert list(services.mis_resultados_publicados(escenario["exp_a"])) == [publicada]


@pytest.mark.django_db
def test_el_rechazo_queda_auditado_al_pasar_por_la_vista(escenario):
    """
    La garantía que importa, ejercida por donde ocurre de verdad.

    `test_un_expediente_no_se_vincula_a_dos_cuentas` llama al servicio directo,
    así que nunca ejerce `ATOMIC_REQUESTS = True`: en producción toda la vista
    es una transacción, y si el ValidationError escapara de ella, el rollback
    se llevaría por delante el propio registro del rechazo —la trampa que
    CLAUDE.md documenta y que ya costó cara dos veces—.

    La vista captura el error y responde con un mensaje, así que la transacción
    de la petición se confirma y el registro sobrevive. Esta prueba lo fija: si
    alguien deja de capturarlo, el rechazo dejaría de auditarse en silencio.
    """
    from apps.auditoria.models import LogAuditoria

    _vincular(escenario["ana"], escenario["exp_a"])

    c = Client()
    c.login(username="beto", password=CLAVE)
    r = c.post("/portal/vincular/", {"cedula": CEDULA_A})

    assert r.status_code in (200, 302)  # respuesta normal, no un 500
    log = LogAuditoria.objects.filter(modulo="portal", resultado="rechazado").first()
    assert log is not None, "el intento rechazado no quedó auditado"
    assert log.usuario == escenario["beto"]
    assert not VinculacionPortal.objects.filter(usuario=escenario["beto"], verificado=True).exists()


@pytest.mark.django_db
def test_el_portal_no_muestra_talleres(escenario):
    """
    Los talleres son trabajo del servicio que los organiza y los ve su personal
    responsable, no quien asiste.

    El panel listaba «Mis talleres» y el barrido de la API eximía a talleres
    como catálogo público. La lista de participantes se conserva —es la base de
    la cobertura que el servicio reporta—, pero no se publica al estudiante.
    """
    from apps.expediente.tests.factories import crear_profesional
    from apps.talleres.models import Taller, TallerParticipante

    _psicologo, perfil = crear_profesional(
        "psi_taller_portal", escenario["est"]["psicologia"], escenario["est"]["psico"]
    )
    taller = Taller.objects.create(
        servicio=escenario["est"]["psicologia"],
        seccion=escenario["est"]["psico"],
        responsable=perfil,
        tema="Manejo del estrés",
        fecha=timezone.localdate(),
    )
    TallerParticipante.objects.create(taller=taller, expediente=escenario["exp_a"])

    _vincular(escenario["ana"], escenario["exp_a"])
    cliente = Client()
    assert cliente.login(username="ana", password=CLAVE)
    contenido = cliente.get("/portal/").content.decode()
    assert "Manejo del estrés" not in contenido
    assert "Mis talleres" not in contenido
