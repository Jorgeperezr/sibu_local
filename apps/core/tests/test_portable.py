"""
El arranque de la portable: la primera cuenta y los ajustes que la sostienen.

Dos cosas que solo se ven ejecutándolo, y que se comprobaron ejecutándolo:

1. **`Usuario.objects.exists()` SIEMPRE es cierto.** La migración de
   django-guardian deja su fila `AnonymousUser`, así que «¿hay alguna cuenta
   todavía?» no se puede preguntar así. El creador de cuentas de la portable lo
   preguntaba de esa forma y nunca reconocía la primera cuenta como primera: la
   creaba con «Consulta Restringida» y quien acababa de instalar el sistema
   entraba y veía seis módulos de diecisiete, sin nadie que pudiera darle más.

2. **Los ajustes portables tienen que escribir dentro de la carpeta.** Es lo
   que hace que copiarla a otro computador —o a una memoria— se lleve la
   instalación entera. Un dato que acabe en el perfil del usuario o en /var se
   queda atrás sin avisar.
"""

import importlib

import pytest
from django.conf import settings

from apps.usuarios.models import Rol, Usuario
from apps.usuarios.selectors import cuentas_de_persona, nombre_del_centinela

CLAVE = "clave-larga-12345"


@pytest.mark.django_db
def test_el_centinela_de_guardian_no_cuenta_como_cuenta():
    """
    Lo que hacía que la primera cuenta no fuera la primera.

    `AnonymousUser` existe desde la migración de guardian, sin que nadie lo
    haya dado de alta.
    """
    assert Usuario.objects.filter(
        username=nombre_del_centinela()
    ).exists(), "la fila de guardian tiene que estar: es la premisa del defecto"
    assert Usuario.objects.exists(), "siempre cierto, y por eso no sirve de pregunta"

    assert not cuentas_de_persona().exists(), "sin personas todavía"


@pytest.mark.django_db
def test_con_una_persona_dada_de_alta_ya_no_es_la_primera():
    Usuario.objects.create_user(username="alguien", password=CLAVE)

    assert cuentas_de_persona().count() == 1


@pytest.mark.django_db
def test_la_cuenta_creada_por_la_portable_queda_fuera_del_centinela():
    """
    El centinela no se puede colar en ninguna lista de personas: ni para
    contarlo, ni para darle ficha, ni para asignarle nada.
    """
    Usuario.objects.create_user(
        username="profesional", password=CLAVE, rol_principal=Rol.PROFESIONAL
    )

    nombres = set(cuentas_de_persona().values_list("username", flat=True))

    assert nombres == {"profesional"}


# ------------------------------------------------------- los ajustes portables


def test_los_ajustes_portables_escriben_dentro_de_la_carpeta(tmp_path, monkeypatch):
    """
    Todo lo que el sistema escribe —base, clave, registro, correo, adjuntos—
    vive junto al código. Es lo que hace que la carpeta se pueda copiar entera.
    """
    monkeypatch.setenv("SIBU_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.portable")

    portable = importlib.import_module("config.settings.portable")
    importlib.reload(portable)

    carpeta = str(tmp_path / "datos")
    assert portable.DATABASES["default"]["NAME"].startswith(carpeta)
    assert portable.MEDIA_ROOT.startswith(carpeta)
    assert portable.EMAIL_FILE_PATH.startswith(carpeta)
    assert portable.LOGGING["handlers"]["archivo"]["filename"].startswith(carpeta)


def test_la_clave_se_genera_una_vez_y_se_conserva(tmp_path, monkeypatch):
    """
    Regenerarla en cada arranque cerraría la sesión cada vez que se abre el
    programa, que es otra forma del mismo error.
    """
    monkeypatch.setenv("SIBU_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.portable")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    portable = importlib.import_module("config.settings.portable")
    importlib.reload(portable)
    primera = portable.SECRET_KEY

    importlib.reload(portable)
    segunda = portable.SECRET_KEY

    assert primera == segunda
    assert len(primera) >= 50, "corta sería un fallo de seguridad, no un detalle"


def test_la_portable_no_escucha_fuera_del_propio_computador(monkeypatch, tmp_path):
    """
    Una portable no es un servidor. Si hay que compartir datos se hace contra
    la instancia central, no abriendo el puerto de la portátil de alguien.
    """
    monkeypatch.setenv("SIBU_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.portable")

    portable = importlib.import_module("config.settings.portable")
    importlib.reload(portable)

    assert portable.ALLOWED_HOSTS == ["127.0.0.1", "localhost"]
    assert "*" not in portable.ALLOWED_HOSTS


def test_el_puerto_del_launcher_entra_en_los_origenes_de_confianza(monkeypatch, tmp_path):
    """
    El launcher elige un puerto libre y lo pasa por entorno ANTES de importar
    los ajustes. Sin eso el sistema levanta, todas las páginas responden y el
    formulario de acceso devuelve 403: el sitio en pie con todo el mundo fuera,
    que es el fallo más caro que ya conocemos de los despliegues.
    """
    monkeypatch.setenv("SIBU_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.portable")
    monkeypatch.setenv("SIBU_ORIGENES", "http://127.0.0.1:8765,http://localhost:8765")

    portable = importlib.import_module("config.settings.portable")
    importlib.reload(portable)

    assert "http://127.0.0.1:8765" in portable.CSRF_TRUSTED_ORIGINS


def test_los_ajustes_de_prueba_no_son_los_portables():
    """
    Una prueba que leyera la configuración del entorno pasaría en una máquina y
    fallaría en otra. Esta fija lo que afirma: la suite NO corre en portable.
    """
    assert settings.SETTINGS_MODULE != "config.settings.portable"
