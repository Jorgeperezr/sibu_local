"""Pruebas del proceso psicológico, escalas y protocolo de riesgo."""

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import Servicio
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.psicologia import services
from apps.psicologia.models import EscalaPsicometrica, FichaPsicologica

PHQ9_TRAMOS = [
    {"min": 0, "max": 4, "etiqueta": "Mínima", "alerta": False},
    {"min": 5, "max": 9, "etiqueta": "Leve", "alerta": False},
    {"min": 10, "max": 14, "etiqueta": "Moderada", "alerta": False},
    {"min": 15, "max": 19, "etiqueta": "Moderada-grave", "alerta": True},
    {"min": 20, "max": 27, "etiqueta": "Grave", "alerta": True},
]


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    psico, _ = Servicio.objects.get_or_create(
        codigo="psicologia", defaults={"nombre": "Psicología", "seccion": est["salud"]}
    )
    # Psicología pertenece a la Sección Psicopedagógica en la estructura real,
    # no a Salud: usar la sección efectiva del servicio, no asumirla.
    _, psicologo = crear_profesional("psicologo", psico, psico.seccion)
    exp = crear_expediente(cedula="1104567894")
    escala = EscalaPsicometrica.objects.create(
        codigo="PHQ-9",
        nombre="Cuestionario de salud del paciente",
        puntaje_min=0,
        puntaje_max=27,
        tramos=PHQ9_TRAMOS,
    )
    return {"est": est, "psico": psico, "psicologo": psicologo, "exp": exp, "escala": escala}


@pytest.mark.django_db
def test_crear_ficha(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    assert ficha.atencion.servicio.codigo == "psicologia"
    assert ficha.estado_proceso == FichaPsicologica.Estado.ACTIVO
    assert ficha.riesgo_nivel == FichaPsicologica.Riesgo.BAJO


@pytest.mark.django_db
def test_motivo_obligatorio(escenario):
    with pytest.raises(ValidationError, match="motivo"):
        services.crear_ficha(
            expediente=escenario["exp"], profesional=escenario["psicologo"], motivo=""
        )


@pytest.mark.django_db
def test_no_dos_procesos_activos(escenario):
    services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    with pytest.raises(ValidationError, match="ya tiene un proceso"):
        services.crear_ficha(
            expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Otro"
        )


@pytest.mark.django_db
def test_sesiones_numeradas_correlativas(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    for i in range(1, 4):
        s = services.registrar_sesion(
            ficha, profesional=escenario["psicologo"], evolucion=f"Sesión {i}"
        )
        assert s.numero == i


@pytest.mark.django_db
def test_evolucion_obligatoria(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    with pytest.raises(ValidationError, match="evolución"):
        services.registrar_sesion(ficha, profesional=escenario["psicologo"], evolucion="")


@pytest.mark.django_db
def test_escala_interpreta_tramo(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    ap = services.aplicar_escala(ficha, "PHQ-9", 3)
    assert ap.interpretacion == "Mínima"
    assert ap.alerta is False

    ap = services.aplicar_escala(ficha, "PHQ-9", 12)
    assert ap.interpretacion == "Moderada"


@pytest.mark.django_db
def test_escala_fuera_de_rango(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    with pytest.raises(ValidationError, match="fuera del rango"):
        services.aplicar_escala(ficha, "PHQ-9", 40)


@pytest.mark.django_db
def test_escala_con_alerta_eleva_riesgo_a_alto(escenario):
    """Un PHQ-9 de 22 (grave) eleva el riesgo automáticamente."""
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    ap = services.aplicar_escala(ficha, "PHQ-9", 22)
    ficha.refresh_from_db()

    assert ap.alerta is True
    assert ficha.riesgo_nivel == FichaPsicologica.Riesgo.ALTO
    assert "PHQ-9" in ficha.nota_riesgo


@pytest.mark.django_db
def test_riesgo_alto_notifica_al_coordinador_sin_contenido(escenario):
    """El coordinador se entera del caso, pero NO del contenido clínico."""
    from apps.notificaciones.models import Notificacion
    from apps.usuarios.models import PerfilProfesional, Rol, Usuario

    coord = Usuario.objects.create_user(
        username="coord", password="x", rol_principal=Rol.COORDINADOR
    )
    # El coordinador debe ser de la sección a la que pertenece Psicología.
    PerfilProfesional.objects.create(usuario=coord, seccion=escenario["psico"].seccion)

    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    services.marcar_riesgo(
        ficha, FichaPsicologica.Riesgo.ALTO, "Ideación suicida activa con plan estructurado."
    )

    noti = Notificacion.objects.filter(tipo="riesgo_psicologia", usuario=coord).first()
    assert noti is not None
    # La notificación avisa del caso...
    assert "riesgo alto" in noti.mensaje.lower()
    # ...pero NO filtra el contenido clínico.
    assert "suicida" not in noti.mensaje.lower()
    assert "plan estructurado" not in noti.mensaje.lower()


@pytest.mark.django_db
def test_riesgo_exige_nota(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    with pytest.raises(ValidationError, match="nota"):
        services.marcar_riesgo(ficha, FichaPsicologica.Riesgo.ALTO, "")


@pytest.mark.django_db
def test_cerrar_exige_al_menos_una_sesion(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    with pytest.raises(ValidationError, match="sin ninguna sesión"):
        services.cerrar_proceso(ficha, FichaPsicologica.Estado.ALTA)

    services.registrar_sesion(ficha, profesional=escenario["psicologo"], evolucion="Trabajo")
    services.cerrar_proceso(ficha, FichaPsicologica.Estado.ALTA)

    ficha.refresh_from_db()
    assert ficha.estado_proceso == FichaPsicologica.Estado.ALTA
    assert ficha.atencion.estado == Atencion.Estado.CERRADA


@pytest.mark.django_db
def test_proceso_cerrado_no_admite_sesiones(escenario):
    ficha = services.crear_ficha(
        expediente=escenario["exp"], profesional=escenario["psicologo"], motivo="Ansiedad"
    )
    services.registrar_sesion(ficha, profesional=escenario["psicologo"], evolucion="Uno")
    services.cerrar_proceso(ficha, FichaPsicologica.Estado.ALTA)
    with pytest.raises(ValidationError, match="no admite nuevas sesiones"):
        services.registrar_sesion(ficha, profesional=escenario["psicologo"], evolucion="Dos")
