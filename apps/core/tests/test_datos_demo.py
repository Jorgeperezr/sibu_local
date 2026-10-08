"""
El comando que siembra datos para probar el sistema.

Se cubre lo que rompería la prueba manual sin avisar: que la cuenta de acceso
exista y funcione, y que vea el contenido clínico. Esto último no es obvio: el
RBAC le niega las atenciones a quien sea administrador, así que la cuenta se
crea con rol profesional a propósito.
"""

import pytest
from django.core.management import call_command
from django.test import Client

from apps.core.management.commands.datos_demo import ADMIN, PACIENTES
from apps.expediente.models import Expediente, Persona
from apps.usuarios.models import Rol, Usuario


@pytest.fixture
def sembrado(db, settings):
    settings.DEBUG = True
    call_command("seed_inicial", verbosity=0)
    call_command("datos_demo", verbosity=0)


@pytest.mark.django_db
def test_los_pacientes_quedan_registrados(sembrado):
    """Que no haya que dar de alta a nadie para empezar a probar."""
    assert Persona.objects.count() >= len(PACIENTES)
    assert Expediente.objects.count() >= len(PACIENTES)


@pytest.mark.django_db
def test_las_cedulas_sembradas_son_validas(sembrado):
    """`Persona.save()` aplica el módulo 10: una cédula inventada no entraría."""
    from apps.academico.validators import validar_cedula_ecuatoriana

    for cedula in Persona.objects.values_list("cedula", flat=True):
        assert validar_cedula_ecuatoriana(cedula), cedula


@pytest.mark.django_db
def test_la_cuenta_de_acceso_entra_con_su_contrasena(sembrado):
    c = Client()
    assert c.login(username=ADMIN["username"], password=ADMIN["clave"])


@pytest.mark.django_db
def test_la_cuenta_de_acceso_ve_los_nueve_servicios(sembrado):
    from apps.core.navegacion import modulos_visibles

    u = Usuario.objects.get(username=ADMIN["username"])
    etiquetas = {m.etiqueta for m in modulos_visibles(u)}
    assert {
        "Medicina",
        "Enfermería",
        "Odontología",
        "Laboratorio",
        "Farmacia",
        "Psicología",
        "Psicopedagogía",
        "Becas",
    } <= etiquetas


@pytest.mark.django_db
def test_la_cuenta_de_acceso_si_ve_el_contenido_clinico(sembrado):
    """
    La razón de que su rol sea PROFESIONAL y no ADMIN_GENERAL.

    `rbac.atenciones_visibles` devuelve un queryset vacío a quien sea
    administrador —incluido cualquier superusuario— por separación de
    funciones. Con rol de administrador, esta cuenta abriría cada expediente y
    vería "0 atenciones visibles": lo contrario de poder probar el sistema.
    """
    u = Usuario.objects.get(username=ADMIN["username"])
    assert u.rol_principal == Rol.PROFESIONAL
    assert not u.is_superuser

    c = Client()
    c.login(username=ADMIN["username"], password=ADMIN["clave"])
    exp = Expediente.objects.filter(atenciones__isnull=False).first()
    cuerpo = c.get(f"/expediente/{exp.pk}/").content.decode()
    assert "No hay atenciones visibles" not in cuerpo


@pytest.mark.django_db
def test_el_comando_es_idempotente(sembrado):
    """Volver a correrlo no duplica pacientes ni cuentas."""
    personas = Persona.objects.count()
    usuarios = Usuario.objects.count()
    call_command("datos_demo", verbosity=0)
    assert Persona.objects.count() == personas
    assert Usuario.objects.count() == usuarios


@pytest.mark.django_db
def test_se_niega_a_correr_en_produccion(db, settings):
    """Pacientes inventados y contraseñas públicas no caben en el servidor real."""
    from django.core.management.base import CommandError

    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG=True"):
        call_command("datos_demo", verbosity=0)
