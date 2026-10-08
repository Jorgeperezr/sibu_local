"""
Todo lo que el menú ofrece tiene que abrirse.

`navegacion.py` lo dice en su encabezado desde el principio: «el menú no debe
poder mostrar un enlace a algo que la vista luego niega con 403». No había nada
que lo comprobara, y no se cumplía: el administrador —la primera cuenta de
cualquier despliegue— veía las nueve bandejas de servicio y las nueve
respondían 403, Psicología entre ellas.

Esto lo barre para varios perfiles. Un 403 aquí no es un permiso mal puesto: es
el menú y la vista diciendo cosas distintas, y quien lo sufre es la persona que
pulsa un enlace muerto en la navegación principal.
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import NoReverseMatch, reverse

from apps.core.navegacion import modulos_visibles
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def estructura(db):
    """
    La estructura REAL, no una reducida. El barrido abre las bandejas de los
    nueve servicios y una vista que no encuentra el suyo revienta con
    `Servicio.DoesNotExist`: sería un fallo del montaje tapando el que se
    busca. `seed_inicial` es lo mismo que corre un despliegue.
    """
    from django.core.management import call_command

    call_command("seed_inicial", verbosity=0)
    return crear_estructura()


def _perfil(nombre, estructura):
    """Una cuenta de cada clase, con su sesión iniciada."""
    if nombre == "admin":
        usuario = Usuario.objects.create_user(
            username="nav_admin", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
        )
    elif nombre == "director":
        usuario = Usuario.objects.create_user(
            username="nav_director", password=CLAVE, rol_principal=Rol.DIRECTOR
        )
    elif nombre == "sin_servicios":
        usuario = Usuario.objects.create_user(username="nav_pelado", password=CLAVE)
    else:
        usuario, _ = crear_profesional("nav_medico", estructura["medicina"], estructura["salud"])
        usuario.set_password(CLAVE)
        usuario.save()

    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return usuario, cliente


@pytest.mark.parametrize("perfil", ["admin", "director", "profesional", "sin_servicios"])
@pytest.mark.django_db
def test_ningun_modulo_del_menu_responde_4xx_a_quien_lo_ve(perfil, estructura):
    usuario, cliente = _perfil(perfil, estructura)

    muertos = []
    for modulo in modulos_visibles(usuario):
        try:
            ruta = reverse(modulo.url_name)
        except NoReverseMatch:
            continue
        # El cliente de pruebas relanza la PermissionDenied en vez de devolver
        # el 403, y esa excepción cortaría el barrido en el primer enlace
        # muerto: se atrapa para poder enseñarlos todos de una vez.
        try:
            estado = cliente.get(ruta).status_code
        except PermissionDenied:
            estado = 403
        if estado >= 400:
            muertos.append(f"{modulo.etiqueta} ({ruta}) -> {estado}")

    assert not muertos, (
        f"El menú de «{perfil}» ofrece enlaces que la vista niega: {muertos}. "
        "Se arregla en la regla del módulo, no abriendo la vista."
    )
