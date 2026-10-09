"""
Lo que la portable instala, y lo que no.

`pip install` es atómico para quien lo mira: si un solo paquete falla, la
carpeta no se arma y el profesional se queda sin sistema. En su computador
—Windows, sin compilador, a veces sin permisos— cada dependencia de más es una
forma de que eso ocurra.

La portable traía `-r base.txt` entera: PostgreSQL (que no usa, porque su base
es SQLite), gunicorn (que **no corre en Windows**, que es justo donde va), la
firma y las bibliotecas de Google (integraciones que vienen deshabilitadas
detrás de un provider).

Lo compartido vive en `comun.txt` para que no haya dos listas de versiones que
se separen con el tiempo: una portable con otro Django que el servidor es un
sistema distinto con el mismo nombre.
"""

import re
from pathlib import Path

REQUISITOS = Path(__file__).resolve().parents[3] / "requirements"

# Solo del servidor. Cada uno con el motivo por el que no puede ir en la
# portable, que es lo que hay que releer antes de volver a meterlo.
SOLO_SERVIDOR = {
    "psycopg": "la portable usa SQLite",
    "gunicorn": "no funciona en Windows; la portable usa waitress",
    "pyhanko": "la firma viene deshabilitada tras su provider",
    "google-api-python-client": "integración deshabilitada por omisión",
    "google-auth": "integración deshabilitada por omisión",
}


def _paquetes(nombre: str) -> set[str]:
    """Los nombres de paquete declarados en un archivo, sin seguir los `-r`."""
    texto = (REQUISITOS / nombre).read_text(encoding="utf-8")
    paquetes = set()
    for linea in texto.splitlines():
        linea = linea.split("#")[0].strip()
        if not linea or linea.startswith("-"):
            continue
        paquetes.add(re.split(r"[\[=<>!~]", linea)[0].strip().lower())
    return paquetes


def _resuelto(nombre: str) -> set[str]:
    """Todo lo que instala ese archivo, siguiendo los `-r`."""
    texto = (REQUISITOS / nombre).read_text(encoding="utf-8")
    todo = _paquetes(nombre)
    for linea in texto.splitlines():
        if linea.strip().startswith("-r "):
            todo |= _resuelto(linea.strip()[3:].strip())
    return todo


def test_la_portable_no_instala_lo_que_es_solo_del_servidor():
    instala = _resuelto("portable.txt")

    for paquete, motivo in SOLO_SERVIDOR.items():
        assert paquete not in instala, f"la portable no necesita {paquete}: {motivo}"


def test_la_portable_lleva_su_servidor_wsgi():
    """Sin esto la carpeta no sirve nada: no hay nginx ni `runserver`."""
    assert "waitress" in _resuelto("portable.txt")


def test_la_portable_lleva_lo_que_importa_al_arrancar():
    """
    Lo que se importa en el momento de cargar los módulos, no al usarse. Si
    falta uno de estos, la portable no levanta —no es que se degrade—.

    `celery` está en la lista a propósito: `apps/citas/tasks.py` hace
    `from celery import shared_task` al importarse, aunque la portable no tenga
    ningún demonio que ejecute nada.
    """
    instala = _resuelto("portable.txt")

    for paquete in (
        "django",
        "djangorestframework",
        "whitenoise",
        "celery",
        "django-celery-beat",
        "django-axes",
        "django-guardian",
        "django-simple-history",
        "drf-spectacular",
    ):
        assert paquete in instala, f"sin {paquete} la portable no arranca"


def test_el_servidor_sigue_llevandolo_todo():
    """La separación no puede quitarle nada al despliegue de verdad."""
    instala = _resuelto("prod.txt")

    for paquete in SOLO_SERVIDOR:
        assert paquete in instala, f"el servidor perdió {paquete}"
    assert "django" in instala


def test_el_ci_instala_lo_mismo_que_el_servidor():
    """
    `dev.txt` es lo que instala el CI. Si deja de traer lo del servidor, una
    prueba que ejercita el almacenamiento de producción falla por no encontrar
    el paquete y no por lo que comprueba. Ya pasó con WhiteNoise.
    """
    del_ci = _resuelto("dev.txt")

    assert _resuelto("prod.txt") - {"sentry-sdk"} <= del_ci


def test_las_versiones_no_estan_declaradas_dos_veces():
    """
    Dos listas de versiones se separan con el tiempo, y una portable con otro
    Django que el servidor es un sistema distinto con el mismo nombre.
    """
    comun = _paquetes("comun.txt")

    assert not (comun & _paquetes("base.txt")), "repetido entre comun.txt y base.txt"
    assert not (comun & _paquetes("portable.txt")), "repetido entre comun.txt y portable.txt"


def test_todo_lo_declarado_lleva_version_fijada():
    """Una versión suelta hace que dos instalaciones del mismo código difieran."""
    for archivo in ("comun.txt", "base.txt", "portable.txt", "prod.txt", "dev.txt"):
        texto = (REQUISITOS / archivo).read_text(encoding="utf-8")
        for linea in texto.splitlines():
            linea = linea.split("#")[0].strip()
            if not linea or linea.startswith("-"):
                continue
            assert "==" in linea, f"{archivo}: «{linea}» sin versión fijada"
