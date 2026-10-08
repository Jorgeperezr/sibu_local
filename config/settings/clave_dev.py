"""
La clave de firma de desarrollo, en un módulo aparte.

Vive fuera de `dev.py` por una razón concreta: importar `dev.py` tiene efectos
—inserta el middleware del debug toolbar y dos apps en las listas que comparte
con `base.py`—, así que una prueba que lo importara para comprobar la clave
alteraría los ajustes del resto de la suite. Aquí no hay nada que alterar.
"""

from __future__ import annotations

from pathlib import Path

ARCHIVO = ".secret_key_dev"


def clave_de_desarrollo(base_dir) -> str:
    """
    Una SECRET_KEY utilizable en desarrollo, generada la primera vez.

    El README pedía `cp .env.example .env`, y ese ejemplo trae `SECRET_KEY=`
    vacía a propósito —es una plantilla de producción—. Con la clave vacía
    Django aborta al importar los ajustes con «The SECRET_KEY setting must not
    be empty»: no arrancaba nada, ni la pantalla de inicio de sesión. En
    desarrollo esa ausencia se resuelve sola.

    Se guarda en un archivo (ignorado por git) en vez de generarse en cada
    arranque: si cambiara, todas las sesiones y los tokens CSRF abiertos
    quedarían invalidados y habría que volver a iniciar sesión tras cada
    reinicio del servidor, que es justo el error que esto viene a quitar.

    `prod.py` NO usa nada de esto: allí una clave ausente debe seguir siendo un
    fallo ruidoso, porque una clave adivinable firma sesiones reales.
    """
    from django.core.management.utils import get_random_secret_key

    archivo = Path(base_dir) / ARCHIVO
    if archivo.exists():
        guardada = archivo.read_text(encoding="utf-8").strip()
        if guardada:
            return guardada
    generada = get_random_secret_key()
    try:
        archivo.write_text(generada, encoding="utf-8")
    except OSError:
        # Sistema de archivos de solo lectura: la clave sirve igual durante
        # este proceso, solo que las sesiones no sobrevivirán al reinicio.
        pass
    return generada
