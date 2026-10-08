"""
`{% estatico %}`: el enlace a un estático con su versión pegada.

El defecto que lo motivó, visto en un Codespace: la hoja de estilos propia se
había quedado en la caché del navegador y este dejó de pedirla. En el registro
del servidor se veía cómo pedía `bootstrap.min.css`, `bootstrap-icons.min.css`
y `montserrat.css` —y no `sibu.css`—, y la pantalla salía sin formato: la
barra lateral desmontada y los enlaces en fila, como si el CSS no existiera.
No se parece a un problema de caché, y por eso cuesta encontrarlo.
"""

from pathlib import Path

import pytest
from django.template import Context, Template

PLANTILLA = Template("{% load estaticos %}{% estatico 'css/sibu.css' %}")


def _pintar():
    return PLANTILLA.render(Context({}))


def test_en_desarrollo_el_enlace_lleva_version(settings):
    settings.DEBUG = True
    url = _pintar()
    assert "css/sibu.css" in url
    assert "?v=" in url


def test_la_version_es_la_del_archivo(settings):
    """
    De la marca de tiempo del archivo, no de un número al azar: si cambiara en
    cada carga, el navegador volvería a descargarlo todo siempre y la caché
    dejaría de servir para nada.
    """
    settings.DEBUG = True
    from apps.core.templatetags.estaticos import _version

    hoja = Path(settings.BASE_DIR) / "static" / "css" / "sibu.css"
    assert _version("css/sibu.css") == str(int(hoja.stat().st_mtime))
    assert _pintar() == _pintar()


def test_en_produccion_no_añade_nada(settings):
    """
    Allí `CompressedManifestStaticFilesStorage` ya entrega nombres con hash, y
    una consulta encima solo estorbaría al cacheado de WhiteNoise.
    """
    settings.DEBUG = False
    assert "?v=" not in _pintar()


def test_un_estatico_inexistente_no_tumba_la_pagina(settings):
    """
    Sin versión el enlace sigue siendo válido. Que falte un archivo es un
    problema; que por eso reviente la plantilla entera, otro peor.
    """
    settings.DEBUG = True
    salida = Template("{% load estaticos %}{% estatico 'css/no-existe.css' %}").render(Context({}))
    assert "no-existe.css" in salida
    assert "?v=" not in salida


@pytest.mark.django_db
def test_la_pagina_sirve_la_hoja_propia_con_version(client, settings):
    """
    Que el tag exista no basta: tiene que estar puesto en `base.html`. Es
    justamente el enlace que se quedó cacheado.
    """
    settings.DEBUG = True
    contenido = client.get("/cuentas/login/").content.decode()
    assert "css/sibu.css?v=" in contenido


@pytest.mark.django_db
def test_todas_las_hojas_y_el_script_van_versionados(settings):
    """
    De poco sirve versionar una sola: si mañana se edita `bootstrap.min.css`
    de la copia local, el navegador se quedaría con la vieja igual.
    """
    raiz = Path(settings.BASE_DIR)
    base = (raiz / "templates" / "base.html").read_text(encoding="utf-8")
    for archivo in (
        "css/sibu.css",
        "vendor/bootstrap/bootstrap.min.css",
        "vendor/bootstrap-icons/bootstrap-icons.min.css",
        "vendor/montserrat/montserrat.css",
        "vendor/bootstrap/bootstrap.bundle.min.js",
    ):
        assert f"{{% estatico '{archivo}' %}}" in base, f"{archivo} sin versionar"
