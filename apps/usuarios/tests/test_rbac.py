"""Pruebas del núcleo RBAC (informe 10)."""

import pytest

from apps.expediente.selectors import timeline
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.usuarios.models import Rol, Usuario


@pytest.mark.django_db
def test_profesional_ve_su_servicio_no_otros():
    e = crear_estructura()
    exp = crear_expediente()
    medico_user, medico = crear_profesional("medico", e["medicina"], e["salud"])
    psi_user, psi = crear_profesional("psico", e["psicologia"], e["psico"])

    at_med = crear_atencion(exp, e["medicina"], medico)
    crear_atencion(exp, e["psicologia"], psi)

    visibles = timeline(exp, medico_user)
    assert at_med in visibles
    # El médico NO ve la atención de Psicología (confidencial)
    assert visibles.filter(servicio__codigo="psicologia").count() == 0


@pytest.mark.django_db
def test_psicologia_no_accesible_por_break_glass():
    e = crear_estructura()
    exp = crear_expediente()
    _, psi = crear_profesional("psico", e["psicologia"], e["psico"])
    crear_atencion(exp, e["psicologia"], psi)

    director = Usuario.objects.create_user(username="dir", password="x", rol_principal=Rol.DIRECTOR)
    # Ni siquiera con break_glass el director ve el contenido de Psicología
    visibles = timeline(exp, director, break_glass=True)
    assert visibles.filter(servicio__codigo="psicologia").count() == 0


@pytest.mark.django_db
def test_admin_no_ve_clinico_por_defecto():
    e = crear_estructura()
    exp = crear_expediente()
    _, medico = crear_profesional("medico", e["medicina"], e["salud"])
    crear_atencion(exp, e["medicina"], medico)

    admin = Usuario.objects.create_user(
        username="admin", password="x", rol_principal=Rol.ADMIN_GENERAL
    )
    assert timeline(exp, admin).count() == 0  # separación de funciones


@pytest.mark.django_db
def test_coordinador_ve_su_seccion():
    e = crear_estructura()
    exp = crear_expediente()
    _, medico = crear_profesional("medico", e["medicina"], e["salud"])
    crear_atencion(exp, e["medicina"], medico)

    coord_user = Usuario.objects.create_user(
        username="coord", password="x", rol_principal=Rol.COORDINADOR
    )
    from apps.usuarios.models import PerfilProfesional

    PerfilProfesional.objects.create(usuario=coord_user, seccion=e["salud"])

    assert timeline(exp, coord_user).filter(servicio__codigo="medicina").count() == 1
