"""
Barrido de las pantallas web, el gemelo del de la API.

El mismo descuido que dejó doce endpoints abiertos dejó pantallas abiertas:
`@login_required` a secas, que solo pregunta si hay sesión, nunca de quién.
El Sprint 7b corrigió nueve vistas así; este barrido recorre el resolver de
URLs para que la décima no haga falta encontrarla a mano.

Lo que encontró al escribirse:

- `/citas/reservar/` — un estudiante reservaba una cita para cualquier
  expediente con cualquier profesional, Psicología incluida.
- `/citas/_persona/` — la tercera puerta a `resolver_por_cedula`, después de
  la vista `buscar` y de la API: devuelve los datos de la persona y de paso le
  ABRE un expediente.
- `/citas/_profesionales/` — el directorio de quién atiende en cada servicio.

Lo que un estudiante SÍ puede abrir se lista con su razón: si mañana aparece
una pantalla nueva en esa lista, hay que justificarla a mano.
"""

import re

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import get_resolver

from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"

# Pantallas que un estudiante debe poder abrir, POR RUTA y con su razón.
#
# Por ruta y no por nombre de URL, y esto importa: `bandeja` es el nombre que
# usan Medicina, Psicología, Laboratorio, Farmacia, Becas, Talleres y
# Derivaciones. Permitir «bandeja» habría abierto la lista blanca a las siete y
# dejado el barrido ciego justo para las pantallas que vino a vigilar.
PERMITIDAS = {
    "/": "portada pública",
    "/cuentas/login/": "iniciar sesión",
    "/cuentas/logout/": "cerrar sesión",
    "/cuentas/password_change/": "cambiar su propia contraseña",
    "/cuentas/password_change/done/": "confirmación de lo anterior",
    "/cuentas/password_reset/": "recuperar su propia contraseña",
    "/cuentas/password_reset/done/": "confirmación de lo anterior",
    "/cuentas/reset/1/1/": "recuperar su propia contraseña",
    "/cuentas/reset/done/": "confirmación de lo anterior",
    "/usuarios/mi-perfil/": "su propia ficha",
    "/portal/vincular/": "portal del estudiante: vincula SU expediente, por identidad",
    # El recordatorio de su propia cita le llega aquí cuando tiene cuenta del
    # portal vinculada. La vista parte del usuario de la sesión, así que solo
    # ve las suyas: aislamiento por identidad, igual que el portal.
    "/notificaciones/": "sus propias notificaciones, filtradas por el usuario de la sesión",
}

# Prefijos que este barrido no cubre: la API tiene el suyo.
FUERA = ("api/", "admin/", "__debug__", "static", "media", "portal/")


def _rutas():
    encontradas = []

    def recorre(patrones, prefijo=""):
        for p in patrones:
            if hasattr(p, "url_patterns"):
                recorre(p.url_patterns, prefijo + str(p.pattern))
            else:
                encontradas.append((prefijo + str(p.pattern), p.name))

    recorre(get_resolver().url_patterns)
    return encontradas


@pytest.fixture
def sembrado(db, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def test_el_barrido_recorre_algo():
    assert len(_rutas()) >= 40


@pytest.mark.django_db
def test_un_estudiante_no_abre_ninguna_pantalla_de_gestion(sembrado):
    """
    Cada 200 inesperado es una pantalla que no pregunta quién entra. No se
    exige un código concreto —302 a login, 403, 404 son todos correctos—:
    se exige que no sea 200.
    """
    Usuario.objects.create_user(username="est_web", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    cliente = Client()
    assert cliente.login(username="est_web", password=CLAVE)

    abiertas = {}
    for patron, nombre in _rutas():
        if patron.startswith(FUERA) or "format" in patron:
            continue
        url = "/" + re.sub(r"<[^>]+>", "1", patron)
        if "(" in url or url in PERMITIDAS:
            continue
        try:
            respuesta = cliente.get(url)
        except Exception:
            # Una vista que revienta con un id inventado no es un agujero de
            # acceso; es otra cosa, y la juzga
            # `test_ninguna_ruta_revienta_con_un_id_que_no_existe`, más abajo.
            continue
        if respuesta.status_code == 200:
            abiertas[url] = nombre

    assert abiertas == {}, f"pantallas abiertas a un estudiante: {abiertas}"


@pytest.mark.django_db
def test_ninguna_ruta_revienta_con_un_id_que_no_existe(sembrado):
    """
    Pedir algo que no está es un 404, nunca una página de error.

    El barrido de acceso de arriba se traga las excepciones a propósito —una
    vista que revienta no es un agujero de permisos—, y esa «otra cosa» no la
    miraba nadie. Aquí sí: se recorren TODAS las rutas con una cuenta que llega
    a casi todo y se exige que ninguna devuelva 5xx ni deje escapar una
    excepción.

    Con un id inventado, lo correcto es 404 (no existe), 403 (no le
    corresponde) o 302 (a iniciar sesión). Un 500 es un fallo del sistema
    delante de quien solo tecleó mal una dirección.
    """
    from apps.core.management.commands.datos_demo import ADMIN

    cliente = Client()
    assert cliente.login(username=ADMIN["username"], password=ADMIN["clave"])

    rotas = []
    for patron, nombre in _rutas():
        if patron.startswith(FUERA) or "format" in patron or "(" in patron:
            continue
        url = "/" + re.sub(r"<[^>]+>", "999999", patron)
        try:
            respuesta = cliente.get(url)
        except Exception as exc:  # noqa: BLE001 - se reporta con su ruta
            rotas.append(f"{url} ({nombre}): {type(exc).__name__}: {exc}")
            continue
        if respuesta.status_code >= 500:
            rotas.append(f"{url} ({nombre}): HTTP {respuesta.status_code}")
    assert rotas == [], "rutas que revientan con un id inexistente: " + "; ".join(rotas)
