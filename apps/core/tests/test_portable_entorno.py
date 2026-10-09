"""
Dos cosas que en producción resuelve el servidor y en una portable no hay quien
resuelva.

1. **Los adjuntos.** En producción los sirve nginx; en desarrollo, Django con
   `DEBUG=True`. Una portable no tiene ni lo uno ni lo otro: `DEBUG=False` y
   sin nginx. El profesional subía una evidencia a un taller y después no
   podía abrirla —404 sobre un archivo que está en su propio disco—.

2. **El PDF.** WeasyPrint necesita librerías del sistema (GTK en Windows) que
   una carpeta portable no lleva. Sin eso, pulsar «Exportar PDF» devolvía un
   500 con un ImportError, y un 500 no le dice a nadie que el informe sí se
   puede ver en pantalla y exportar a Excel.
"""

import importlib

import pytest
from django.urls import clear_url_caches, reverse

from apps.core.pdf import PdfNoDisponible

# ---------------------------------------------------------------- adjuntos


def _rutas_con(settings_mod, **ajustes):
    """Recarga el enrutador con otros ajustes y devuelve sus rutas."""
    for clave, valor in ajustes.items():
        setattr(settings_mod, clave, valor)
    import config.urls

    importlib.reload(config.urls)
    clear_url_caches()
    return config.urls.urlpatterns


def test_la_portable_sirve_sus_propios_adjuntos(settings):
    """
    Sin esto se sube una evidencia y no se puede abrir: 404 sobre un archivo
    que está en el disco de quien lo subió.
    """
    try:
        rutas = _rutas_con(settings, DEBUG=False, SIBU_PORTABLE=True)
        patrones = [str(r.pattern) for r in rutas]
        assert any(
            settings.MEDIA_URL.lstrip("/") in p for p in patrones
        ), "la portable no está sirviendo /media/"
    finally:
        _rutas_con(settings, DEBUG=False, SIBU_PORTABLE=False)


def test_un_servidor_de_produccion_no_sirve_los_adjuntos_con_django(settings):
    """Ahí es trabajo de nginx, y Django sirviéndolos sería el error contrario."""
    try:
        rutas = _rutas_con(settings, DEBUG=False, SIBU_PORTABLE=False)
        patrones = [str(r.pattern) for r in rutas]
        assert not any(settings.MEDIA_URL.lstrip("/") in p for p in patrones)
    finally:
        _rutas_con(settings, DEBUG=False, SIBU_PORTABLE=False)


# --------------------------------------------------------------------- PDF


def test_sin_weasyprint_se_dice_en_vez_de_reventar(monkeypatch):
    """
    Una instalación sin las librerías del sistema no es un fallo del sistema:
    es una condición del entorno, y la pantalla tiene que decirla.
    """
    import builtins

    real = builtins.__import__

    def sin_weasyprint(nombre, *args, **kwargs):
        if nombre == "weasyprint":
            raise ImportError("No module named 'weasyprint'")
        return real(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sin_weasyprint)

    from apps.core.pdf import render_pdf

    with pytest.raises(PdfNoDisponible, match="no puede generar PDFs"):
        render_pdf("reportes/tablero_pdf.html", {})


def test_el_mensaje_ofrece_la_alternativa():
    """Decir que no se puede sin decir qué sí se puede deja al usuario parado."""
    error = PdfNoDisponible(
        "Este SIBU no puede generar PDFs: falta WeasyPrint o las librerías "
        "del sistema que necesita. El informe se puede ver en pantalla y "
        "exportar a Excel."
    )

    assert "pantalla" in str(error)
    assert "Excel" in str(error)


@pytest.mark.django_db
def test_la_vista_del_tablero_avisa_en_vez_de_devolver_500(client, monkeypatch):
    """Lo que de verdad importa: que el profesional vea un aviso, no un 500."""
    from django.core.management import call_command

    from apps.usuarios.models import Rol, Usuario

    call_command("seed_inicial", verbosity=0)
    Usuario.objects.create_user(
        username="dir_pdf", password="clave-larga-12345", rol_principal=Rol.DIRECTOR
    )
    assert client.login(username="dir_pdf", password="clave-larga-12345")

    import apps.reportes.views as vistas

    def no_hay_pdf(*args, **kwargs):
        raise PdfNoDisponible("Este SIBU no puede generar PDFs: falta WeasyPrint.")

    monkeypatch.setattr(vistas, "render_pdf", no_hay_pdf)

    respuesta = client.get(reverse("reportes:exportar_pdf"), follow=True)

    assert respuesta.status_code == 200
    assert "no puede generar PDFs" in respuesta.content.decode()
