"""
Los orígenes que CSRF acepta en desarrollo, en un módulo aparte.

Vive fuera de `dev.py` por lo mismo que `clave_dev.py`: importar el módulo de
ajustes tiene efectos —inserta el middleware del debug toolbar y dos apps en
las listas que comparte con `base.py`—, así que una prueba que lo importara
para comprobar esta lista alteraría los ajustes del resto de la suite.
"""

from __future__ import annotations

# Puerto en el que sirve `scripts/dev.sh`. Django no admite comodín de puerto
# en CSRF_TRUSTED_ORIGINS (el `*` solo vale en la etiqueta izquierda del host),
# así que el puerto hay que nombrarlo. Quien sirva en otro debe exportar
# CSRF_TRUSTED_ORIGINS, que es lo que hace `dev.sh`.
PUERTO_POR_DEFECTO = "8000"


def origenes_confiables(entorno, puerto: str = PUERTO_POR_DEFECTO) -> list[str]:
    """
    Orígenes de confianza para desarrollo: lo declarado más lo inevitable.

    Antes `dev.py` fijaba la lista a mano con dos comodines, e ignoraba la
    variable `CSRF_TRUSTED_ORIGINS` que `scripts/dev.sh` se molestaba en
    calcular: la derivación del dominio de Codespaces era código muerto. Aquí
    se lee primero lo declarado en el entorno, y se le suma lo que hace falta
    siempre.

    Entre eso último va `https://localhost:<puerto>`, y no es adorno: el
    reenvío de puertos de Codespaces presenta ese Origin aunque la barra del
    navegador muestre el dominio `*.app.github.dev`. Sin él la página carga, se
    ve el formulario de inicio de sesión, y al enviarlo responde «La
    verificación CSRF ha fallado» sin decir por qué.

    Solo desarrollo. `prod.py` exige CSRF_TRUSTED_ORIGINS explícito y no añade
    nada por su cuenta: confiar en localhost detrás de un proxy real sería
    aceptar como propio el origen de cualquiera que alcance el servidor.
    """
    declarados = [
        origen.strip()
        for origen in (entorno.get("CSRF_TRUSTED_ORIGINS") or "").split(",")
        if origen.strip()
    ]

    codespace = entorno.get("CODESPACE_NAME")
    dominio_reenvio = entorno.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    propios = []
    if codespace and dominio_reenvio:
        propios.append(f"https://{codespace}-{puerto}.{dominio_reenvio}")

    propios += [
        "https://*.app.github.dev",
        "https://*.githubpreview.dev",
        f"https://localhost:{puerto}",
        f"http://localhost:{puerto}",
        f"https://127.0.0.1:{puerto}",
        f"http://127.0.0.1:{puerto}",
    ]

    # Sin repetir y conservando el orden: lo declarado manda, y una lista con
    # duplicados solo hace más difícil leer de dónde salió cada entrada.
    vistos: set[str] = set()
    resultado = []
    for origen in declarados + propios:
        if origen not in vistos:
            vistos.add(origen)
            resultado.append(origen)
    return resultado
