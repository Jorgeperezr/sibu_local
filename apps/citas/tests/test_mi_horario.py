"""
El profesional configura cuándo atiende y cuánto dura su consulta.

`Agenda` existía entera desde el Sprint 3 —día, horas, duración, vigencia— y
solo se tocaba desde el panel de administración de Django o desde el shell.
Quien atiende no podía declarar sus propios días, y de esa tabla sale TODO el
agendamiento: los turnos que ve ventanilla y la duración que se graba en cada
cita. El motor estaba; faltaba el volante.

Lo que se prueba es la regla, no el formulario.
"""

from datetime import time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.citas import services
from apps.citas.models import Agenda
from apps.citas.selectors import citas_fuera_del_horario
from apps.citas.tests.factories import escenario_basico
from apps.expediente.tests.factories import crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    esc = escenario_basico()
    usuario = esc["medico"].usuario
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    esc["cliente"] = cliente
    return esc


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_no_se_puede_dar_horario_en_un_servicio_ajeno(escenario):
    """
    El horario dice que se atiende ahí. Un profesional de Medicina que se
    diera franja en Psicología aparecería en los turnos de Psicología.
    """
    with pytest.raises(ValidationError, match="No atiende en ese servicio"):
        services.guardar_franja(
            profesional=escenario["medico"],
            servicio=escenario["est"]["psicologia"],
            dia_semana=1,
            hora_inicio=time(8, 0),
            hora_fin=time(12, 0),
            duracion_turno_min=20,
        )
    assert not Agenda.objects.filter(servicio=escenario["est"]["psicologia"]).exists()


# ------------------------------------------------------------------- encajes


@pytest.mark.django_db
def test_una_consulta_que_no_cabe_en_la_franja_se_rechaza(escenario):
    """
    Sin esto la franja se guardaba y no producía ni un turno: la pantalla de
    reserva decía «sin turnos disponibles» y no había manera de saber por qué.
    """
    with pytest.raises(ValidationError, match="no cabe en una franja"):
        services.guardar_franja(
            profesional=escenario["medico"],
            servicio=escenario["est"]["medicina"],
            dia_semana=1,
            hora_inicio=time(8, 0),
            hora_fin=time(8, 30),
            duracion_turno_min=60,
        )


@pytest.mark.django_db
def test_la_hora_de_fin_tiene_que_ir_despues(escenario):
    with pytest.raises(ValidationError, match="anterior a la de fin"):
        services.guardar_franja(
            profesional=escenario["medico"],
            servicio=escenario["est"]["medicina"],
            dia_semana=1,
            hora_inicio=time(12, 0),
            hora_fin=time(8, 0),
            duracion_turno_min=20,
        )


@pytest.mark.django_db
@pytest.mark.parametrize("duracion", [1, 600])
def test_la_duracion_tiene_limites(escenario, duracion):
    """Menos de cinco minutos no es una consulta; más de cuatro horas no es un turno."""
    with pytest.raises(ValidationError, match="minutos"):
        services.guardar_franja(
            profesional=escenario["medico"],
            servicio=escenario["est"]["medicina"],
            dia_semana=1,
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            duracion_turno_min=duracion,
        )


# ------------------------------------------------------------------- choques


@pytest.mark.django_db
def test_dos_franjas_del_mismo_dia_no_se_pueden_pisar(escenario):
    """
    La persona es una: no puede estar el lunes a las 09:00 en dos sitios. Sin
    esta comprobación las dos pantallas ofrecían el mismo turno y la segunda
    reserva moría con «el turno ya está ocupado», que no explica nada.
    """
    with pytest.raises(ValidationError, match="Se pisa con su franja"):
        services.guardar_franja(
            profesional=escenario["medico"],
            servicio=escenario["est"]["medicina"],
            dia_semana=0,  # el escenario ya tiene lunes de 08:00 a 12:00
            hora_inicio=time(10, 0),
            hora_fin=time(14, 0),
            duracion_turno_min=20,
        )


@pytest.mark.django_db
def test_una_franja_puede_empezar_cuando_acaba_otra(escenario):
    """El extremo derecho es abierto: 12:00–16:00 pegado a 08:00–12:00 cabe."""
    franja = services.guardar_franja(
        profesional=escenario["medico"],
        servicio=escenario["est"]["medicina"],
        dia_semana=0,
        hora_inicio=time(12, 0),
        hora_fin=time(16, 0),
        duracion_turno_min=20,
    )
    assert franja.pk


@pytest.mark.django_db
def test_dos_franjas_que_no_comparten_vigencia_no_chocan(escenario):
    """Un horario de este semestre no pisa al del semestre que viene."""
    vieja = escenario["agenda"]
    corte = vieja.vigente_desde + timedelta(days=30)
    vieja.vigente_hasta = corte
    vieja.save()

    nueva = services.guardar_franja(
        profesional=escenario["medico"],
        servicio=escenario["est"]["medicina"],
        dia_semana=0,
        hora_inicio=time(9, 0),
        hora_fin=time(13, 0),
        duracion_turno_min=20,
        vigente_desde=corte + timedelta(days=1),
    )
    assert nueva.pk != vieja.pk


@pytest.mark.django_db
def test_editar_una_franja_no_choca_consigo_misma(escenario):
    """Se excluye del choque la que se está editando, o nada sería editable."""
    franja = escenario["agenda"]
    services.guardar_franja(
        profesional=escenario["medico"],
        servicio=escenario["est"]["medicina"],
        dia_semana=0,
        hora_inicio=time(8, 0),
        hora_fin=time(13, 0),
        duracion_turno_min=30,
        franja=franja,
    )
    franja.refresh_from_db()
    assert franja.duracion_turno_min == 30
    assert franja.hora_fin == time(13, 0)


# ------------------------------------------------------------------- retirar


@pytest.mark.django_db
def test_retirar_una_franja_no_la_borra(escenario):
    """
    Las citas ya reservadas apuntan al horario que regía cuando se reservaron;
    borrar la franja dejaría el calendario sin explicar de dónde salieron.
    """
    services.retirar_franja(escenario["agenda"])

    escenario["agenda"].refresh_from_db()
    assert escenario["agenda"].activa is False
    assert Agenda.objects.filter(pk=escenario["agenda"].pk).exists()
    assert (
        services.turnos_disponibles(
            escenario["medico"], escenario["est"]["medicina"], escenario["lunes"]
        )
        == []
    )


# ---------------------------------------------------- lo que queda por fuera


@pytest.mark.django_db
def test_estrechar_el_horario_avisa_de_las_citas_que_quedan_fuera(escenario):
    """
    El sistema informa; la decisión es del profesional. Sin este aviso la cita
    desaparecía de los turnos ofrecidos y seguía viva en la agenda del día: el
    paciente se presentaba a una consulta que ya no estaba prevista.
    """
    turnos = services.turnos_disponibles(
        escenario["medico"], escenario["est"]["medicina"], escenario["lunes"]
    )
    tarde = [t for t in turnos if timezone.localtime(t).hour >= 11][0]
    cita = services.reservar_cita(
        expediente=escenario["exp"],
        servicio=escenario["est"]["medicina"],
        profesional=escenario["medico"],
        fecha_hora=tarde,
    )
    assert citas_fuera_del_horario(escenario["medico"]) == []

    # Ahora solo atiende hasta las 10:00.
    services.guardar_franja(
        profesional=escenario["medico"],
        servicio=escenario["est"]["medicina"],
        dia_semana=0,
        hora_inicio=time(8, 0),
        hora_fin=time(10, 0),
        duracion_turno_min=20,
        franja=escenario["agenda"],
    )

    fuera = citas_fuera_del_horario(escenario["medico"])
    assert [c.pk for c in fuera] == [cita.pk]
    cita.refresh_from_db()
    assert cita.estado == cita.Estado.RESERVADA, "estrechar el horario no cancela a nadie"


# ------------------------------------------------------------------ pantalla


@pytest.mark.django_db
def test_la_pantalla_lista_el_horario_propio(escenario):
    contenido = escenario["cliente"].get(reverse("citas:mi_horario")).content.decode()

    assert "Lunes" in contenido
    assert "08:00" in contenido
    # Los turnos que caben: el número que se quiere saber al cambiar la duración.
    assert "12" in contenido


@pytest.mark.django_db
def test_se_anade_una_franja_desde_la_pantalla(escenario):
    respuesta = escenario["cliente"].post(
        reverse("citas:mi_horario"),
        {
            "servicio": escenario["est"]["medicina"].pk,
            "dia_semana": 2,
            "hora_inicio": "14:00",
            "hora_fin": "18:00",
            "duracion": "30",
        },
        follow=True,
    )

    assert respuesta.status_code == 200
    franja = Agenda.objects.get(profesional=escenario["medico"], dia_semana=2)
    assert franja.duracion_turno_min == 30
    assert franja.turnos_por_dia == 8


@pytest.mark.django_db
def test_no_se_toca_la_franja_de_otro(escenario):
    """Un id en el POST no es un permiso."""
    otro_usuario, otro = crear_profesional(
        "otro_medico", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    ajena = Agenda.objects.create(
        profesional=otro,
        servicio=escenario["est"]["medicina"],
        dia_semana=3,
        hora_inicio=time(8, 0),
        hora_fin=time(12, 0),
        duracion_turno_min=20,
    )

    respuesta = escenario["cliente"].post(
        reverse("citas:mi_horario"), {"accion": "retirar", "franja": ajena.pk}
    )

    assert respuesta.status_code == 404
    ajena.refresh_from_db()
    assert ajena.activa is True


@pytest.mark.django_db
def test_quien_no_atiende_no_tiene_horario_que_configurar(db):
    """Ventanilla reserva citas, no las atiende: no tiene franjas propias."""
    Usuario.objects.create_user(
        username="ventanilla", password=CLAVE, rol_principal=Rol.ADMINISTRATIVO
    )
    cliente = Client()
    assert cliente.login(username="ventanilla", password=CLAVE)

    assert cliente.get(reverse("citas:mi_horario")).status_code == 403


@pytest.mark.django_db
def test_un_formulario_incompleto_avisa_y_no_revienta(escenario):
    respuesta = escenario["cliente"].post(
        reverse("citas:mi_horario"),
        {"servicio": escenario["est"]["medicina"].pk, "dia_semana": 2},
        follow=True,
    )

    assert respuesta.status_code == 200
    assert not Agenda.objects.filter(dia_semana=2).exists()


@pytest.mark.django_db
def test_el_menu_ofrece_mi_horario_a_quien_atiende(escenario):
    from apps.core.navegacion import modulos_visibles

    etiquetas = {m.etiqueta for m in modulos_visibles(escenario["medico"].usuario)}

    assert "Mi horario" in etiquetas


@pytest.mark.django_db
def test_el_menu_no_lo_ofrece_a_quien_no_tiene_perfil(db):
    """Ofrecerlo a ventanilla sería un enlace al 403 de arriba."""
    from apps.core.navegacion import modulos_visibles

    usuario = Usuario.objects.create_user(
        username="ventanilla2", password=CLAVE, rol_principal=Rol.ADMINISTRATIVO
    )
    etiquetas = {m.etiqueta for m in modulos_visibles(usuario)}

    assert "Mi horario" not in etiquetas
    assert "Mi agenda" in etiquetas, "ventanilla sigue viendo lo suyo"


# ------------------------------------------- la duración manda en el agendamiento


@pytest.mark.django_db
def test_la_duracion_de_la_agenda_manda_en_la_cita(escenario):
    """
    El defecto que motiva todo esto. `reservar_cita` llevaba `duracion_min=20`
    por omisión y ninguna pantalla lo sobrescribía: con consultas de 40 minutos
    configuradas, la pantalla ofrecía turnos cada 40 —eso sí lo respetaba— y
    grababa la cita de 20. SIBU daba por libre la segunda mitad de cada
    consulta y admitía un segundo paciente encima del primero.
    """
    agenda = escenario["agenda"]
    agenda.duracion_turno_min = 40
    agenda.save()

    turnos = services.turnos_disponibles(
        escenario["medico"], escenario["est"]["medicina"], escenario["lunes"]
    )
    cita = services.reservar_cita(
        expediente=escenario["exp"],
        servicio=escenario["est"]["medicina"],
        profesional=escenario["medico"],
        fecha_hora=turnos[0],
    )

    assert cita.duracion_min == 40
    assert cita.fin == turnos[0] + timedelta(minutes=40)
    # Y la consecuencia: el minuto 20 ya no está libre.
    assert services._hay_solapamiento(
        escenario["medico"], turnos[0] + timedelta(minutes=20), turnos[0] + timedelta(minutes=60)
    )


@pytest.mark.django_db
def test_una_duracion_expresa_sigue_mandando(escenario):
    """Reprogramar conserva la duración de la cita original."""
    turnos = services.turnos_disponibles(
        escenario["medico"], escenario["est"]["medicina"], escenario["lunes"]
    )
    cita = services.reservar_cita(
        expediente=escenario["exp"],
        servicio=escenario["est"]["medicina"],
        profesional=escenario["medico"],
        fecha_hora=turnos[0],
        duracion_min=15,
    )

    assert cita.duracion_min == 15


@pytest.mark.django_db
def test_una_consulta_que_se_sale_del_horario_se_rechaza(escenario):
    """No es un turno: es trabajo fuera de hora que nadie aceptó."""
    turnos = services.turnos_disponibles(
        escenario["medico"], escenario["est"]["medicina"], escenario["lunes"]
    )
    ultimo = turnos[-1]  # 11:40, y el horario acaba a las 12:00

    with pytest.raises(ValidationError, match="no cabe antes de las"):
        services.reservar_cita(
            expediente=escenario["exp"],
            servicio=escenario["est"]["medicina"],
            profesional=escenario["medico"],
            fecha_hora=ultimo,
            duracion_min=60,
        )


@pytest.mark.django_db
def test_un_turno_ocupado_no_se_vuelve_a_ofrecer_aunque_no_coincida_el_inicio(escenario):
    """
    Ocupado es solapar, no empezar en el mismo minuto. Comparar la igualdad
    exacta de `fecha_hora` bastaba mientras todas las citas duraban lo mismo;
    en cuanto el profesional cambia la duración deja de bastar.
    """
    turnos = services.turnos_disponibles(
        escenario["medico"], escenario["est"]["medicina"], escenario["lunes"]
    )
    services.reservar_cita(
        expediente=escenario["exp"],
        servicio=escenario["est"]["medicina"],
        profesional=escenario["medico"],
        fecha_hora=turnos[0],
        duracion_min=60,  # 08:00–09:00, tres turnos de veinte
    )

    libres = services.turnos_disponibles(
        escenario["medico"], escenario["est"]["medicina"], escenario["lunes"]
    )
    horas = {timezone.localtime(t).strftime("%H:%M") for t in libres}

    assert "08:20" not in horas
    assert "08:40" not in horas
    assert "09:00" in horas


@pytest.mark.django_db
def test_los_turnos_llegan_con_su_hora_ya_escrita(escenario):
    """
    La hora la dice el servidor, no el navegador.

    El desplegable de reserva la componía con `toLocaleString`, que usa la zona
    horaria DEL EQUIPO: en uno mal configurado ofrecía «02:00 p. m.» para el
    turno de las 09:00 y, tras guardar, el aviso confirmaba «09:00». La misma
    cita con dos horas distintas en la misma pantalla, y quien elige sin manera
    de saber cuál vale. La agenda se define en hora de Loja y el servidor ya la
    conoce.

    Lo que esto fija es que la etiqueta VIAJE ya escrita y en hora de Loja, una
    por turno. Que el navegador no la recalcule es lo que se arregla; esta
    prueba lo sostiene porque sin la etiqueta la plantilla no tiene de dónde
    sacarla.
    """
    respuesta = escenario["cliente"].get(
        "/api/v1/citas/disponibilidad/",
        {
            "profesional": escenario["medico"].pk,
            "servicio": escenario["est"]["medicina"].pk,
            "fecha": escenario["lunes"].isoformat(),
        },
    )
    datos = respuesta.json()

    assert datos["etiquetas"][:3] == ["08:00", "08:20", "08:40"]
    assert len(datos["etiquetas"]) == len(datos["turnos"])


@pytest.mark.django_db
def test_las_franjas_vigentes_van_antes_que_las_retiradas(escenario):
    """El horario que rige es lo que se viene a ver."""
    from apps.citas.selectors import franjas_del_profesional

    services.retirar_franja(escenario["agenda"])
    services.guardar_franja(
        profesional=escenario["medico"],
        servicio=escenario["est"]["medicina"],
        dia_semana=4,
        hora_inicio=time(8, 0),
        hora_fin=time(12, 0),
        duracion_turno_min=20,
    )

    activas = [f.activa for f in franjas_del_profesional(escenario["medico"])]

    assert activas == sorted(activas, reverse=True)
