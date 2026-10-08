"""
Pruebas del sello de confidencialidad de Psicología.

Decisión funcional del cliente (Sprint 7): el contenido de Psicología es
inaccesible para cualquiera que no sea el equipo del propio servicio.
NI SIQUIERA la Dirección de Bienestar puede verlo, bajo ninguna circunstancia,
incluyendo el acceso de emergencia (break-the-glass).

Estas pruebas son la garantía ejecutable de esa decisión: si alguien relaja el
RBAC en el futuro, fallan.
"""

import pytest

from apps.expediente.selectors import timeline
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.usuarios import rbac
from apps.usuarios.models import Rol, Usuario


@pytest.fixture
def escenario(db):
    from apps.core.models import Servicio

    est = crear_estructura()
    psico, _ = Servicio.objects.get_or_create(
        codigo="psicologia", defaults={"nombre": "Psicología", "seccion": est["salud"]}
    )
    _, psicologo = crear_profesional("psicologo", psico, psico.seccion)
    _, medico = crear_profesional("medico_otro", est["medicina"], est["salud"])

    exp = crear_expediente(cedula="1104567894")
    atencion_psico = crear_atencion(exp, psico, psicologo)
    atencion_med = crear_atencion(exp, est["medicina"], medico)

    return {
        "est": est,
        "psico_servicio": psico,
        "psicologo": psicologo,
        "medico": medico,
        "exp": exp,
        "atencion_psico": atencion_psico,
        "atencion_med": atencion_med,
    }


def _usuario_con_rol(username, rol, servicio=None, seccion=None):
    """Crea un usuario con el rol dado; si hay servicio, le arma el perfil."""
    from apps.usuarios.models import PerfilProfesional

    user = Usuario.objects.create_user(username=username, password="clave12345", rol_principal=rol)
    if servicio is not None:
        perfil = PerfilProfesional.objects.create(usuario=user, seccion=seccion or servicio.seccion)
        perfil.servicios.add(servicio)  # servicios es M2M
    return user


@pytest.mark.django_db
def test_director_no_ve_psicologia_ni_con_break_glass(escenario):
    """La Dirección de Bienestar NO accede a Psicología. Nunca."""
    director = _usuario_con_rol("director", Rol.DIRECTOR)

    assert rbac.puede_ver_atencion(director, escenario["atencion_psico"]) is False
    assert rbac.puede_ver_atencion(director, escenario["atencion_psico"], break_glass=True) is False

    from apps.expediente.models import Atencion

    visibles = rbac.atenciones_visibles(director, Atencion.objects.all(), break_glass=True)
    assert escenario["atencion_psico"] not in visibles


@pytest.mark.django_db
def test_coordinador_no_ve_psicologia_ni_con_break_glass(escenario):
    coordinador = _usuario_con_rol(
        "coordinador", Rol.COORDINADOR, escenario["est"]["medicina"], escenario["est"]["salud"]
    )

    assert rbac.puede_ver_atencion(coordinador, escenario["atencion_psico"]) is False
    assert (
        rbac.puede_ver_atencion(coordinador, escenario["atencion_psico"], break_glass=True) is False
    )


@pytest.mark.django_db
def test_medico_de_otro_servicio_no_ve_psicologia(escenario):
    """Un médico con break-the-glass ve todo el expediente MENOS psicología."""
    from apps.expediente.models import Atencion

    medico_user = escenario["medico"].usuario

    assert rbac.puede_ver_atencion(medico_user, escenario["atencion_psico"]) is False
    assert (
        rbac.puede_ver_atencion(medico_user, escenario["atencion_psico"], break_glass=True) is False
    )

    visibles = rbac.atenciones_visibles(medico_user, Atencion.objects.all(), break_glass=True)
    assert escenario["atencion_med"] in visibles  # sí ve lo demás
    assert escenario["atencion_psico"] not in visibles  # nunca psicología


@pytest.mark.django_db
def test_admin_no_ve_psicologia(escenario):
    admin = _usuario_con_rol("admin_general", Rol.ADMIN_GENERAL)
    assert rbac.puede_ver_atencion(admin, escenario["atencion_psico"]) is False
    assert rbac.puede_ver_atencion(admin, escenario["atencion_psico"], break_glass=True) is False


@pytest.mark.django_db
def test_psicologo_si_ve_psicologia_de_su_servicio(escenario):
    """El equipo de Psicología sí accede: sin esto el servicio no puede operar."""
    from apps.expediente.models import Atencion

    psico_user = escenario["psicologo"].usuario

    assert rbac.puede_ver_atencion(psico_user, escenario["atencion_psico"]) is True
    visibles = rbac.atenciones_visibles(psico_user, Atencion.objects.all())
    assert escenario["atencion_psico"] in visibles


@pytest.mark.django_db
def test_lista_y_detalle_son_consistentes(escenario):
    """
    Regresión: `atenciones_visibles` no debe listar nada que
    `puede_ver_atencion` luego niegue. Si la lista lo muestra, el detalle
    debe abrirlo.
    """
    from apps.expediente.models import Atencion

    for username, rol, servicio in [
        ("d2", Rol.DIRECTOR, None),
        ("c2", Rol.COORDINADOR, escenario["est"]["medicina"]),
        ("p2", Rol.PROFESIONAL, escenario["psico_servicio"]),
        ("m2", Rol.PROFESIONAL, escenario["est"]["medicina"]),
    ]:
        user = _usuario_con_rol(username, rol, servicio)
        for break_glass in (False, True):
            visibles = rbac.atenciones_visibles(
                user, Atencion.objects.all(), break_glass=break_glass
            )
            for atencion in visibles:
                assert rbac.puede_ver_atencion(user, atencion, break_glass=break_glass), (
                    f"{username} ({rol}) ve #{atencion.pk} ({atencion.servicio.codigo}) "
                    f"en la lista pero el detalle lo niega (break_glass={break_glass})"
                )


@pytest.mark.django_db
def test_timeline_del_expediente_oculta_psicologia_a_terceros(escenario):
    """La línea de tiempo del expediente no filtra psicología a un tercero."""
    eventos = timeline(escenario["exp"], escenario["medico"].usuario, break_glass=True)
    servicios = {e.servicio.codigo for e in eventos}
    assert "psicologia" not in servicios
    assert "medicina" in servicios
