"""
El comando perfil_dev.

Reemplaza el bloque de shell que fallaba al adivinar campos. Las pruebas que
importan son dos: que asigne de verdad todos los servicios, y que se niegue a
correr en producción (porque el perfil que crea viola el sello de Psicología).
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.models import Servicio
from apps.expediente.tests.factories import crear_estructura
from apps.usuarios.models import PerfilProfesional, Rol, Usuario


@pytest.fixture
def estructura(db):
    crear_estructura()
    return Servicio.objects.count()


@pytest.mark.django_db
def test_da_perfil_con_todos_los_servicios(estructura, settings):
    settings.DEBUG = True
    u = Usuario.objects.create_superuser(username="jorgeperez", password="x" * 12)
    call_command("perfil_dev", "--usuario", "jorgeperez")

    u.refresh_from_db()
    assert u.rol_principal == Rol.ADMIN_GENERAL
    perfil = PerfilProfesional.objects.get(usuario=u)
    assert perfil.servicios.count() == estructura == Servicio.objects.count()


@pytest.mark.django_db
def test_se_niega_en_produccion(estructura, settings):
    """
    El perfil ve Psicología: no debe poder crearse con DEBUG=False. Que el
    comando exista no puede ser una puerta trasera en el servidor real.
    """
    settings.DEBUG = False
    Usuario.objects.create_superuser(username="jorgeperez", password="x" * 12)
    with pytest.raises(CommandError, match="DEBUG=True"):
        call_command("perfil_dev", "--usuario", "jorgeperez")
    assert not PerfilProfesional.objects.exists()


@pytest.mark.django_db
def test_usa_el_unico_superusuario_si_no_se_indica(estructura, settings):
    settings.DEBUG = True
    Usuario.objects.create_superuser(username="unico", password="x" * 12)
    call_command("perfil_dev")
    assert PerfilProfesional.objects.filter(usuario__username="unico").exists()


@pytest.mark.django_db
def test_exige_elegir_si_hay_varios_superusuarios(estructura, settings):
    settings.DEBUG = True
    Usuario.objects.create_superuser(username="uno", password="x" * 12)
    Usuario.objects.create_superuser(username="dos", password="x" * 12)
    with pytest.raises(CommandError, match="varios superusuarios"):
        call_command("perfil_dev")


@pytest.mark.django_db
def test_usuario_inexistente_da_error_claro(estructura, settings):
    settings.DEBUG = True
    with pytest.raises(CommandError, match="No existe el usuario"):
        call_command("perfil_dev", "--usuario", "fantasma")


@pytest.mark.django_db
def test_es_idempotente(estructura, settings):
    """Ejecutarlo dos veces no duplica el perfil ni los servicios."""
    settings.DEBUG = True
    Usuario.objects.create_superuser(username="jorgeperez", password="x" * 12)
    call_command("perfil_dev", "--usuario", "jorgeperez")
    call_command("perfil_dev", "--usuario", "jorgeperez")
    assert PerfilProfesional.objects.filter(usuario__username="jorgeperez").count() == 1
    perfil = PerfilProfesional.objects.get(usuario__username="jorgeperez")
    assert perfil.servicios.count() == Servicio.objects.count()
