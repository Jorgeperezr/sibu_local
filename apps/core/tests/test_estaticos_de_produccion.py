"""
Los archivos estáticos tienen que poder recolectarse.

En producción se sirven con `CompressedManifestStaticFilesStorage`, que hace
dos cosas: renombra cada archivo con el hash de su contenido y **sigue las
referencias internas** —los `url()` de un CSS, el `sourceMappingURL` de un JS—.
Si una referencia apunta a algo que no está, `collectstatic` aborta.

Pasó: los Bootstrap vendorizados apuntaban a sus sourcemaps y los `.map` no se
habían vendorizado. Y el Dockerfile llevaba `|| true`, así que la imagen se
construía igual y el sitio arrancaba **sin estáticos**, con cada página
lanzando un ValueError por el manifiesto ausente. Un fallo de construcción
visible convertido en un fallo de producción invisible.

Esta prueba recolecta de verdad, con el mismo almacenamiento de producción, en
un directorio temporal.
"""

import pathlib
import re

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_collectstatic_de_produccion_no_falla(tmp_path, settings):
    """
    El ensayo de lo que hace el Dockerfile al construir la imagen.

    Si esto falla, la imagen no se construye —ya no hay `|| true`— y el fallo
    se ve en el despliegue, no en la cara del usuario.
    """
    settings.STATIC_ROOT = str(tmp_path / "static")
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    call_command("collectstatic", "--noinput", verbosity=0)

    manifiesto = tmp_path / "static" / "staticfiles.json"
    assert manifiesto.exists(), "no se generó el manifiesto: las plantillas darían 500"
    assert (tmp_path / "static" / "css").exists()


RAIZ = pathlib.Path(__file__).resolve().parents[3]
VENDOR = RAIZ / "static" / "vendor"

# `//# sourceMappingURL=` en un JS, `/*# sourceMappingURL= */` en un CSS.
SOURCEMAP = re.compile(r"[/*]#\s*sourceMappingURL=(\S+)")


@pytest.mark.parametrize(
    "archivo",
    sorted(p for p in VENDOR.rglob("*") if p.suffix in {".js", ".css"}),
    ids=lambda p: p.name,
)
def test_ningun_vendorizado_referencia_un_sourcemap_ausente(archivo):
    """
    La causa concreta del fallo, para que se vea al añadir la próxima librería.

    Un sourcemap sirve para depurar el código fuente de una librería que no
    tenemos, así que en producción no aporta nada; lo que sí hace es romper la
    recolección si se referencia y no está. O se vendoriza el `.map`, o se
    retira la línea que lo nombra.
    """
    texto = archivo.read_text(errors="replace")
    for referencia in SOURCEMAP.findall(texto):
        destino = (archivo.parent / referencia).resolve()
        assert destino.exists(), (
            f"{archivo.name} nombra el sourcemap «{referencia}» y no está: "
            "`collectstatic` abortará. Vendorice el .map o quite la línea."
        )
