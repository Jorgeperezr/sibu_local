"""
Generación de documentos PDF con la línea gráfica institucional.

Un solo punto de entrada para todo el sistema: el membrete, la tipografía y los
colores viven en `documentos/base_pdf.html`, y cada documento solo aporta su
contenido. Así un informe de atención y un reporte de gestión salen con la
misma cara, que es la de la UNL.

WeasyPrint resuelve las rutas del HTML contra `base_url`; una URL como
`/static/img/unl-horizontal.png` apuntaría a la raíz del sistema de archivos y
no al proyecto. Por eso el logotipo y las tipografías se pasan resueltos a
`file://` con `ruta_estatica()`, en vez de confiar en `{% static %}`.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.utils import timezone


def ruta_estatica(relativa: str) -> str:
    """URL `file://` de un archivo estático, o cadena vacía si no está."""
    absoluta = finders.find(relativa)
    if absoluta is None and settings.STATIC_ROOT:
        candidata = Path(settings.STATIC_ROOT) / relativa
        absoluta = str(candidata) if candidata.exists() else None
    return Path(absoluta).as_uri() if absoluta else ""


def contexto_institucional(**extra) -> dict:
    """Membrete, marca y sello de tiempo comunes a todos los documentos."""
    contexto = {
        "logo_unl": ruta_estatica("img/unl-horizontal.png"),
        "fuentes": {
            peso: ruta_estatica(f"vendor/montserrat/montserrat-{peso}-latin.woff2")
            for peso in (300, 400, 600, 700)
        },
        # Hora local: un documento fechado en UTC confunde a quien lo archiva.
        "generado_en": timezone.localtime(),
        "institucion": "Universidad Nacional de Loja",
        "unidad": "Unidad de Bienestar Universitario",
    }
    contexto.update(extra)
    return contexto


def render_pdf(plantilla: str, contexto: dict) -> bytes:
    """
    Renderiza una plantilla a PDF con el membrete institucional.

    Importación diferida: WeasyPrint arrastra librerías del sistema y no debe
    exigirse para correr las pruebas que no generan PDFs.
    """
    from weasyprint import HTML

    html = render_to_string(plantilla, contexto_institucional(**contexto))
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
