"""
Barrido de toda la superficie de la API, no de un endpoint a la vez.

Dos mitades: lo que se lee y lo que se escribe. La segunda no la cubre el
filtrado del queryset —un POST no pasa por él—, y ahí un estudiante llegó a
concederse una beca y a crear la agenda de un profesional.

Los agujeros de control de acceso aparecieron de uno en uno —nueve vistas web,
después la trazabilidad de derivaciones, después la lista de citas— y siempre
por el mismo camino: alguien registra un ViewSet nuevo con `IsAuthenticated` y
sin filtrar el queryset, y nadie vuelve a mirarlo.

Esta prueba recorre el router, así que un ViewSet registrado mañana entra solo.
Fija el mínimo que no se negocia: quien solo tiene una sesión —rol
USUARIO_FINAL, la cuenta de un estudiante— no lee datos de pacientes por
ninguna de las puertas registradas. Su propia información la ve por el portal,
que aísla por identidad.

**Siembra el sistema entero antes de mirar.** Sin datos, todas las listas
salen vacías y la prueba pasaría afirmando nada: sería peor que no tenerla,
porque daría por revisada una superficie que nadie revisó.

No comprueba que cada endpoint aplique su regla fina; comprueba que ninguno se
haya quedado sin ninguna.
"""

import pytest
from django.core.management import call_command
from django.test import Client

from api.v1.urls import router
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"

# Catálogos: no contienen datos de personas. Que un estudiante los lea no dice
# nada de nadie, y el portal necesita alguno. Se listan uno a uno, con su
# razón, para que añadir una excepción cueste pensarlo.
CATALOGOS = {
    "farmacia/medicamentos": "vademécum de la Unidad, sin pacientes",
    "laboratorio/examenes": "catálogo de exámenes, sin resultados",
    "odontologia/catalogo": "catálogo de procedimientos",
    "psicologia/escalas": "catálogo de escalas psicométricas, sin aplicaciones",
    "becas/tipos": "tipos de beca ofertados",
}


@pytest.fixture
def sistema_sembrado(db, settings):
    """
    El sistema con actividad real en cada módulo: pacientes, atenciones,
    citas, recetas, órdenes de laboratorio, fichas, derivaciones y becas.
    """
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def _rutas():
    return [(prefijo, viewset.__name__) for prefijo, viewset, _b in router.registry]


def test_el_barrido_recorre_algo():
    """Si el router se reorganiza y esto queda vacío, la prueba pasaría sola."""
    assert len(_rutas()) >= 20


@pytest.mark.django_db
def test_hay_datos_que_filtrar(sistema_sembrado):
    """
    La prueba de abajo afirma «vacío». Esto comprueba que el vacío significa
    algo: que con una cuenta que sí puede ver, esos mismos endpoints traen
    filas. Sin esto, un fallo de siembra convertiría el barrido en un adorno.
    """
    from apps.core.management.commands.datos_demo import ADMIN

    cliente = Client()
    assert cliente.login(username=ADMIN["username"], password=ADMIN["clave"])

    con_filas = []
    for prefijo, _ in _rutas():
        respuesta = cliente.get(f"/api/v1/{prefijo}/")
        if respuesta.status_code != 200:
            continue
        datos = respuesta.json()
        filas = datos["results"] if isinstance(datos, dict) and "results" in datos else datos
        if filas:
            con_filas.append(prefijo)
    assert len(con_filas) >= 5, f"la siembra dejó casi todo vacío: {con_filas}"


@pytest.mark.django_db
def test_un_estudiante_no_lee_datos_de_pacientes_por_ninguna_puerta(sistema_sembrado):
    """
    O responde 403, o devuelve una lista vacía. Lo que no puede es devolver
    filas: cada una llevaría el nombre o la cédula de una persona atendida.
    """
    Usuario.objects.create_user(
        username="sonda_api", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    cliente = Client()
    assert cliente.login(username="sonda_api", password=CLAVE)

    filtraron = {}
    for prefijo, nombre_viewset in _rutas():
        if prefijo in CATALOGOS:
            continue
        respuesta = cliente.get(f"/api/v1/{prefijo}/")
        if respuesta.status_code != 200:
            continue
        datos = respuesta.json()
        filas = datos["results"] if isinstance(datos, dict) and "results" in datos else datos
        if filas:
            filtraron[f"/api/v1/{prefijo}/ ({nombre_viewset})"] = len(filas)

    assert filtraron == {}, f"le devolvieron filas a un estudiante: {filtraron}"


@pytest.mark.django_db
def test_un_estudiante_no_escribe_por_ninguna_puerta(sistema_sembrado):
    """
    Filtrar el queryset no protege el `create`: un POST no pasa por él. Y un
    405 o un 400 no son protección, son casualidad —el primero dice que ese
    verbo no existe, el segundo que la autorización dejó pasar y solo falló el
    serializer—. Con una carga válida, ese 400 es un 201.

    Se comprobó: un estudiante se concedía una beca
    (`POST /becas/beneficiarios/` -> 201) y creaba la agenda de un profesional
    (`POST /agendas/` -> 201).

    Lo que se exige es que la autorización responda antes que la validación:
    403 o 405, nunca 400.
    """
    Usuario.objects.create_user(username="sonda_w", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    cliente = Client()
    assert cliente.login(username="sonda_w", password=CLAVE)

    dejaron_pasar = {}
    for prefijo, nombre_viewset in _rutas():
        respuesta = cliente.post(f"/api/v1/{prefijo}/", "{}", content_type="application/json")
        if respuesta.status_code not in (403, 405):
            dejaron_pasar[f"POST /api/v1/{prefijo}/ ({nombre_viewset})"] = respuesta.status_code

    assert dejaron_pasar == {}, f"la autorización no rechazó: {dejaron_pasar}"


# ------------------------------------------- un parámetro basura no es un 500

# Lo que se cuela por la barra de direcciones. Cada uno rompe una conversión
# distinta: el texto rompe `int()`, la coma rompe `Decimal()` y `int()`, el
# vacío rompe a quien da por hecho que si el parámetro llega trae algo, y el
# número enorme desborda a quien lo mete en un campo con tope.
#
# No hay comillas ni SQL aquí a propósito: el ORM parametriza y esto no
# probaría lo que parecería estar probando.
BASURA = ["abc", "8,5", "", "-1", "99999999999999999999"]

# Parámetros que de verdad se leen en la API. Se listan explícitamente —y no se
# inventan— para que la prueba pruebe lo que existe.
PARAMETROS = ["dias", "periodo", "expediente", "servicio", "page", "page_size", "estado"]


@pytest.mark.django_db
def test_ningun_parametro_mal_escrito_devuelve_una_pagina_de_error(sistema_sembrado):
    """
    Un parámetro de la URL puede traer cualquier cosa.

    `int(request.query_params.get("dias", 90))` devolvía un 500 con
    `?dias=abc`: la conversión no tenía red y la excepción salía sin capturar.
    Una cifra ilegible es una consulta mal escrita —400, o el valor por
    defecto—, nunca una avería del servidor.

    Se recorre el router entero para que un endpoint nuevo entre solo: este
    defecto se escribe sin querer cada vez que alguien lee un parámetro.
    """
    from apps.core.management.commands.datos_demo import ADMIN

    # `raise_request_exception=False`: por omisión el cliente de pruebas
    # RELANZA la excepción de la vista en vez de devolver el 500 que vería un
    # navegador, así que el barrido se detendría en el primer endpoint y
    # ocultaría los demás. Aquí interesa la lista completa.
    cliente = Client(raise_request_exception=False)
    assert cliente.login(username=ADMIN["username"], password=ADMIN["clave"])

    reventaron = []
    for ruta, nombre_viewset in _rutas_consultables():
        for parametro in PARAMETROS:
            for valor in BASURA:
                respuesta = cliente.get(ruta, {parametro: valor})
                if respuesta.status_code >= 500:
                    reventaron.append(f"{nombre_viewset} {ruta}?{parametro}={valor!r}")
    assert reventaron == [], "parámetros que devuelven 500: " + ", ".join(reventaron)


def _rutas_consultables():
    """
    Las listas de cada ViewSet Y sus acciones de lista.

    Las acciones —`@action(detail=False)`, como `/citas/proximas/`— no aparecen
    en el prefijo del router y ahí vivían dos de los tres 500 encontrados:
    recorrer solo las listas habría dado por revisada una superficie que nadie
    revisó, que es el defecto que estos barridos existen para no repetir.
    """
    rutas = []
    for prefijo, viewset, _base in router.registry:
        rutas.append((f"/api/v1/{prefijo}/", viewset.__name__))
        for atributo in dir(viewset):
            metodo = getattr(viewset, atributo, None)
            mapeo = getattr(metodo, "mapping", None)
            if getattr(metodo, "detail", None) is False and mapeo and "get" in mapeo:
                nombre_url = getattr(metodo, "url_path", atributo)
                rutas.append((f"/api/v1/{prefijo}/{nombre_url}/", viewset.__name__))
    return rutas


@pytest.mark.django_db
def test_un_filtro_ilegible_no_devuelve_todo(sistema_sembrado):
    """
    La otra mitad de la corrección, y la que importa.

    `?expediente=abc` reventaba con un 500. Convertirlo en «sin filtro» habría
    quitado el error y dejado algo peor: la respuesta traería las fichas de
    TODAS las personas a quien pidió las de una. Un 400 dice que no se
    entendió; devolver de más dice otra cosa.
    """
    from apps.core.management.commands.datos_demo import ADMIN

    cliente = Client()
    assert cliente.login(username=ADMIN["username"], password=ADMIN["clave"])

    respuesta = cliente.get("/api/v1/trabajo-social/fichas/", {"expediente": "abc"})
    assert respuesta.status_code == 400, respuesta.status_code
