"""
`{% estatico %}`: como `{% static %}`, pero con la versión del archivo pegada.

En desarrollo, `runserver` sirve los estáticos con su nombre de siempre. El
navegador —y, en Codespaces, el reenvío de puertos que hay delante— se queda
con la copia en caché y no vuelve a pedirla: se edita la hoja de estilos, se
recarga, y la página sigue con los estilos viejos. Peor todavía, puede quedarse
con una copia a medias y la pantalla aparece sin formato, como si el CSS no
existiera. Cuesta horas porque no se parece a un problema de caché.

Con `?v=<marca de tiempo>` la URL cambia en cuanto cambia el archivo, así que
la copia vieja deja de servir sola.

En producción NO añade nada: allí `CompressedManifestStaticFilesStorage` ya
entrega nombres con hash, y una consulta encima solo estorbaría al cacheado de
WhiteNoise.
"""

from __future__ import annotations

from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

registro = template.Library()
register = registro  # Django busca el nombre en inglés.


def _version(ruta: str) -> str:
    """Marca de tiempo del archivo, o cadena vacía si no se puede averiguar."""
    try:
        encontrado = finders.find(ruta)
        if not encontrado:
            return ""
        return str(int(Path(encontrado).stat().st_mtime))
    except OSError:
        # Un estático que no se puede leer no debe tumbar la página entera:
        # sin versión, el enlace sigue siendo válido.
        return ""


@registro.simple_tag
def estatico(ruta: str) -> str:
    url = static(ruta)
    if not settings.DEBUG:
        return url
    version = _version(ruta)
    if not version:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}v={version}"
