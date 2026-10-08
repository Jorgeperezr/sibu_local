"""
El arranque en Codespaces.

Lo que se levantaba a mano dejaba dos formas de quedarse fuera del sistema, y
ninguna se explicaba sola:

- Copiar `.env.example` a `.env`, como pedía el README, dejaba `SECRET_KEY`
  vacía y Django abortaba al importar los ajustes: no arrancaba ni la pantalla
  de inicio de sesión.
- Arrancar sobre una base sin preparar levantaba el servidor y luego rechazaba
  cualquier usuario que se escribiera, porque no había ninguna cuenta creada.

Estas pruebas fijan lo que resuelve cada cosa. Siguiendo la disciplina de
`test_checks.py`, fijan lo que afirman en vez de heredarlo del entorno.
"""

from pathlib import Path

import pytest
from django.core.management import call_command

from apps.core.models import Servicio
from apps.usuarios.models import Usuario

# --------------------------------------------------------- clave de desarrollo


# Se importa `clave_dev`, no `dev`: importar el módulo de ajustes de desarrollo
# tiene efectos —inserta el middleware del debug toolbar y dos apps en las
# listas que comparte con `base.py`—, y hacerlo desde una prueba alteraría los
# ajustes del resto de la suite. Por eso la función vive en un módulo aparte.
def test_la_clave_de_desarrollo_se_genera_si_no_hay_ninguna(tmp_path):
    """Sin esto, un `.env` con SECRET_KEY vacía impedía arrancar."""
    from config.settings.clave_dev import clave_de_desarrollo

    clave = clave_de_desarrollo(tmp_path)
    assert clave
    assert len(clave) >= 32


def test_la_clave_de_desarrollo_no_cambia_entre_arranques(tmp_path):
    """
    Si cambiara en cada arranque, las sesiones y los tokens CSRF abiertos
    quedarían invalidados y habría que volver a iniciar sesión tras cada
    reinicio del servidor: justo el error que esto viene a quitar.
    """
    from config.settings.clave_dev import clave_de_desarrollo

    assert clave_de_desarrollo(tmp_path) == clave_de_desarrollo(tmp_path)
    assert (tmp_path / ".secret_key_dev").exists()


def test_una_clave_guardada_vacia_se_regenera(tmp_path):
    """Un archivo truncado no puede dejar el sistema sin clave."""
    from config.settings.clave_dev import clave_de_desarrollo

    (tmp_path / ".secret_key_dev").write_text("   ", encoding="utf-8")
    assert clave_de_desarrollo(tmp_path).strip()


def test_la_clave_generada_no_se_versiona():
    """
    Una clave de firma en el repositorio deja de ser un secreto. Está en
    desarrollo, pero la costumbre de versionarla es la que luego llega a
    producción.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]
    assert ".secret_key_dev" in (raiz / ".gitignore").read_text(encoding="utf-8")


# ------------------------------------------------------------------- preparar


@pytest.mark.django_db
def test_preparar_deja_la_base_utilizable(settings):
    """
    Estructura, permisos y al menos una cuenta con la que iniciar sesión: los
    tres motivos por los que el sistema parecía roto al primer arranque.
    """
    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    assert Servicio.objects.count() == 9
    assert Usuario.objects.exclude(username="AnonymousUser").exists()


@pytest.mark.django_db
def test_preparar_se_puede_repetir_sin_duplicar(settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    servicios = Servicio.objects.count()
    usuarios = Usuario.objects.count()
    call_command("preparar", verbosity=0)
    assert Servicio.objects.count() == servicios
    assert Usuario.objects.count() == usuarios


@pytest.mark.django_db
def test_preparar_sin_demo_no_siembra_pacientes():
    from apps.expediente.models import Persona

    call_command("preparar", "--sin-demo", verbosity=0)
    assert Servicio.objects.count() == 9
    assert not Persona.objects.exists()


@pytest.mark.django_db
def test_preparar_omite_la_demo_en_produccion(settings):
    """
    Los datos de demostración traen contraseñas conocidas y pacientes
    inventados: en un servidor real serían una puerta abierta con historias
    clínicas falsas dentro del expediente único.
    """
    from apps.expediente.models import Persona

    settings.DEBUG = False
    call_command("preparar", verbosity=0)
    assert Servicio.objects.count() == 9  # la estructura sí se prepara
    assert not Persona.objects.exists()


# -------------------------------------------------------------------- cuentas


@pytest.mark.django_db
def test_cuentas_lista_lo_que_existe(capsys, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    capsys.readouterr()  # descartar lo que imprimió la preparación
    call_command("cuentas")
    salida = capsys.readouterr().out
    # Un profesional real de la Unidad y la clave de las cuentas de prueba.
    assert "jhoely.lalangui" in salida
    assert "sibu-demo-2026" in salida


@pytest.mark.django_db
def test_cuentas_no_anuncia_contrasenas_fuera_de_desarrollo(capsys, settings):
    """
    Con DEBUG=False la base no es de demostración: anunciar ahí unas
    contraseñas conocidas sería una invitación a probarlas.
    """
    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    capsys.readouterr()  # descartar lo que imprimió la preparación
    settings.DEBUG = False
    call_command("cuentas")
    salida = capsys.readouterr().out
    assert "jhoely.lalangui" in salida
    assert "sibu-demo-2026" not in salida


@pytest.mark.django_db
def test_cuentas_avisa_cuando_no_hay_ninguna(capsys):
    Usuario.objects.all().delete()
    call_command("cuentas")
    assert "nadie puede iniciar sesión" in capsys.readouterr().out


@pytest.mark.django_db
def test_la_siembra_deja_una_cuenta_que_administra_sin_ver_lo_clinico(settings):
    """
    Separación de funciones, comprobada y no solo declarada.

    La cuenta con acceso a los nueve servicios tiene rol PROFESIONAL para poder
    ver atenciones; con solo esa, nadie llegaba a la base institucional, que
    pide ADMIN_GENERAL. Y darle ese rol la habría dejado ciega ante el contenido
    clínico. Son dos cuentas porque son dos funciones.
    """
    from apps.usuarios.models import Rol

    settings.DEBUG = True
    call_command("preparar", verbosity=0)

    administrador = Usuario.objects.get(username="administrador")
    assert administrador.rol_principal == Rol.ADMIN_GENERAL
    assert administrador.is_superuser is False

    from apps.core.management.commands.datos_demo import ADMIN

    con_servicios = Usuario.objects.get(username=ADMIN["username"])
    assert con_servicios.rol_principal == Rol.PROFESIONAL


@pytest.mark.django_db
def test_quien_administra_alcanza_el_padron_y_quien_atiende_no(settings, client):
    """
    Que el rol exista no basta: la pantalla tiene que abrirse. Y la de al lado,
    no: `medico` es profesional, y el padrón institucional no es suyo.
    """
    from django.urls import reverse

    settings.DEBUG = True
    call_command("preparar", verbosity=0)

    assert client.login(username="administrador", password="sibu-demo-2026")
    assert client.get(reverse("academico:padron")).status_code == 200

    # Un profesional: el padrón institucional no es suyo. Su contraseña es su
    # propio usuario, que es como se siembran los profesionales de la Unidad.
    assert client.login(username="jhoely.lalangui", password="jhoely.lalangui")
    assert client.get(reverse("academico:padron")).status_code == 302


def test_ninguna_prueba_importa_los_ajustes_de_desarrollo():
    """
    Importar `config.settings.dev` desde una prueba inserta el middleware del
    debug toolbar y dos apps en las listas que ese módulo comparte con
    `base.py`. Bajo los ajustes de prueba esas listas son las que Django está
    usando, así que la importación altera la configuración del RESTO de la
    suite: las pruebas que vinieran después harían peticiones a través de un
    middleware que no les corresponde, y el fallo aparecería lejos de su causa.

    Esta prueba estuvo a punto de hacer justo eso. Se queda para que la
    siguiente no lo repita.
    """
    import re
    from pathlib import Path

    # Solo sentencias de importación, no la prosa: este mismo archivo nombra el
    # módulo al explicar por qué no debe importarse.
    patron = re.compile(
        r"^\s*(?:import\s+config\.settings\.dev|from\s+config\.settings(?:\.dev)?\s+import\s+(?:dev\b|\*))",
        re.MULTILINE,
    )
    raiz = Path(__file__).resolve().parents[2]
    culpables = [
        str(archivo.relative_to(raiz))
        for archivo in raiz.rglob("test_*.py")
        if patron.search(archivo.read_text(encoding="utf-8"))
    ]
    assert not culpables, f"importan los ajustes de desarrollo: {culpables}"


# ------------------------------------------------- la cuenta de administración


@pytest.mark.django_db
def test_la_cuenta_de_administracion_entra_con_su_cedula(settings, client):
    """
    Usuario y contraseña son la cédula: es como el modelo `Usuario` dice que se
    identifica una cuenta ("username = cédula o usuario institucional").
    """
    from apps.core.management.commands.datos_demo import ADMIN

    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    assert client.login(username=ADMIN["username"], password=ADMIN["clave"])
    assert Usuario.objects.get(username=ADMIN["username"]).cedula == ADMIN["cedula"]


@pytest.mark.django_db
def test_la_cuenta_de_administracion_sigue_viendo_contenido_clinico(settings):
    """
    Lo que impide convertirla en superusuario de verdad.

    `rbac.atenciones_visibles` devuelve `.none()` para cualquier administrador
    —`es_admin()` cubre `is_superuser` y `ADMIN_GENERAL`— por separación de
    funciones. Con cualquiera de los dos, esta cuenta abriría cada expediente y
    vería «0 atenciones»: lo contrario de poder probar el sistema. Por eso lleva
    rol PROFESIONAL con los nueve servicios, y el acceso a /admin/ va con
    permisos explícitos en vez de `is_superuser`.
    """
    from apps.core.management.commands.datos_demo import ADMIN
    from apps.expediente.models import Atencion
    from apps.usuarios import rbac
    from apps.usuarios.models import Rol

    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    cuenta = Usuario.objects.get(username=ADMIN["username"])

    assert cuenta.rol_principal == Rol.PROFESIONAL
    assert cuenta.is_superuser is False
    assert cuenta.is_staff is True  # entra a /admin/ por permisos explícitos
    assert cuenta.perfil.servicios.count() == 9

    visibles = rbac.atenciones_visibles(cuenta, Atencion.objects.all())
    assert visibles.exists(), "la cuenta de administración se quedó sin ver atenciones"


@pytest.mark.django_db
def test_la_cedula_de_la_cuenta_no_choca_al_resembrar(settings):
    """
    `Usuario.cedula` es única. Si una siembra anterior se la dejó a otra cuenta,
    volver a sembrar reventaría con IntegrityError en vez de reasignarla.
    """
    from apps.core.management.commands.datos_demo import ADMIN

    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    intruso = Usuario.objects.create_user(username="intruso", password="clave-larga-12345")
    Usuario.objects.filter(pk=Usuario.objects.get(username=ADMIN["username"]).pk).update(
        cedula=None
    )
    intruso.cedula = ADMIN["cedula"]
    intruso.save(update_fields=["cedula"])

    call_command("datos_demo", verbosity=0)  # no debe reventar
    assert Usuario.objects.get(username=ADMIN["username"]).cedula == ADMIN["cedula"]
    intruso.refresh_from_db()
    assert intruso.cedula is None


# ------------------------------------------- profesionales de la Unidad


@pytest.mark.django_db
def test_cada_profesional_entra_con_lo_que_va_antes_de_la_arroba(settings, client):
    """
    Lo pedido: el usuario es la parte local de su correo institucional y la
    contraseña es la misma. `jorge.perez@unl.edu.ec` -> usuario y contraseña
    `jorge.perez`.
    """
    from apps.core.management.commands.datos_demo import PROFESIONALES, clave_de

    settings.DEBUG = True
    call_command("preparar", verbosity=0)

    reales = [p for p in PROFESIONALES if p["correo"]]
    assert len(reales) == 5
    for datos in reales:
        local = datos["correo"].split("@")[0]
        assert datos["usuario"] == local
        assert clave_de(datos) == local
        assert client.login(username=local, password=local), f"no entra {local}"


@pytest.mark.django_db
def test_cada_profesional_queda_en_su_servicio_y_con_su_nombre(settings):
    from apps.core.management.commands.datos_demo import PROFESIONALES

    settings.DEBUG = True
    call_command("preparar", verbosity=0)

    for datos in (p for p in PROFESIONALES if p["correo"]):
        cuenta = Usuario.objects.get(username=datos["usuario"])
        assert cuenta.email == datos["correo"]
        assert cuenta.get_full_name() == f"{datos['nombres']} {datos['apellidos']}"
        servicios = list(cuenta.perfil.servicios.values_list("codigo", flat=True))
        assert servicios == [datos["servicio"]], f"{datos['usuario']} ve {servicios}"


@pytest.mark.django_db
def test_el_psicologo_no_es_administrador(settings):
    """
    Jorge Pérez tiene dos cuentas y no son intercambiables: `jorge.perez`
    atiende Psicología, y la de administración es la de su cédula. Si la de
    Psicología llevara rol de administrador, el RBAC le negaría el contenido
    clínico de su propio servicio.
    """
    from apps.core.management.commands.datos_demo import ADMIN
    from apps.usuarios.models import Rol

    settings.DEBUG = True
    call_command("preparar", verbosity=0)

    psicologo = Usuario.objects.get(username="jorge.perez")
    assert psicologo.rol_principal == Rol.PROFESIONAL
    assert psicologo.is_superuser is False
    assert psicologo.is_staff is False
    assert psicologo.pk != Usuario.objects.get(username=ADMIN["username"]).pk


@pytest.mark.django_db
def test_resembrar_corrige_una_cuenta_que_ya_existia(settings):
    """
    Los datos se escriben fuera de `defaults`: si no, `get_or_create` los
    ignoraría en una cuenta ya creada y `make demo` no serviría para corregir
    un nombre mal escrito ni para reponer una contraseña olvidada.
    """
    settings.DEBUG = True
    call_command("preparar", verbosity=0)

    cuenta = Usuario.objects.get(username="daniel.cabrera")
    cuenta.first_name = "Equivocado"
    cuenta.email = ""
    cuenta.set_password("otra-cosa")
    cuenta.save()

    call_command("datos_demo", verbosity=0)
    cuenta.refresh_from_db()
    assert cuenta.first_name == "Daniel Francisco"
    assert cuenta.email == "daniel.cabrera@unl.edu.ec"
    assert cuenta.check_password("daniel.cabrera")


# --------------------------------------------------- preparar --si-cambio


@pytest.mark.django_db
def test_si_cambio_prepara_la_base_vacia(settings):
    """Primer arranque: no hay nada, así que hay que hacerlo todo."""
    settings.DEBUG = True
    call_command("preparar", "--si-cambio", verbosity=0)
    assert Servicio.objects.exists()
    assert Usuario.objects.exists()


@pytest.mark.django_db
def test_si_cambio_no_vuelve_a_sembrar_si_nada_cambio(settings, monkeypatch):
    """
    Lo que hace usable el arranque: en el caso normal —la base ya preparada y
    el código sin tocar— no repite cinco comandos, solo mira una huella.
    """
    from apps.core.management.commands import preparar as modulo

    settings.DEBUG = True
    call_command("preparar", "--si-cambio", verbosity=0)

    llamadas = []
    monkeypatch.setattr(modulo, "call_command", lambda *a, **k: llamadas.append(a[0]))
    call_command("preparar", "--si-cambio", verbosity=0)
    assert llamadas == [], f"volvió a ejecutar {llamadas} sin que nada cambiara"


@pytest.mark.django_db
def test_si_cambio_vuelve_a_sembrar_cuando_la_siembra_cambia(settings, monkeypatch):
    """
    El caso que quita el `make demo` a mano: tras un `git pull` que trae una
    cuenta nueva, el arranque lo nota solo. Antes, no acordarse de sembrar se
    parecía mucho a «las credenciales no funcionan».
    """
    from apps.core.management.commands import preparar as modulo

    settings.DEBUG = True
    call_command("preparar", "--si-cambio", verbosity=0)

    # Como si `datos_demo.py` hubiera cambiado de contenido.
    monkeypatch.setattr(modulo.Command, "_huella", lambda self: "otra-huella")

    llamadas = []
    monkeypatch.setattr(modulo, "call_command", lambda *a, **k: llamadas.append(a[0]))
    call_command("preparar", "--si-cambio", verbosity=0)
    assert "datos_demo" in llamadas
    assert "configurar_rbac" in llamadas


@pytest.mark.django_db
def test_la_huella_mira_el_contenido_y_no_la_fecha(settings, tmp_path):
    """
    `git pull` reescribe las fechas de todos los archivos que toca, aunque el
    contenido sea idéntico. Una huella por fecha volvería a sembrar en cada
    arranque y el remedio sería peor que la enfermedad.
    """
    from apps.core.management.commands.preparar import Command

    orden = Command()
    primera = orden._huella()
    for relativo in Command.ARCHIVOS_DE_SIEMBRA:
        ruta = Path(settings.BASE_DIR) / relativo
        ruta.touch()
    assert orden._huella() == primera


@pytest.mark.django_db
def test_si_cambio_no_da_por_al_dia_una_base_a_medio_preparar(settings, monkeypatch):
    """
    La huella se anota al final. Si un paso revienta a mitad, la base queda
    incompleta y el arranque siguiente tiene que volver a intentarlo; darla por
    al día dejaría el sistema roto sin decirlo.
    """
    from apps.core.management.commands import preparar as modulo
    from apps.core.models import ParametroSistema

    settings.DEBUG = True

    def revienta(nombre, *a, **k):
        if nombre == "cargar_cie10":
            raise RuntimeError("catálogo ilegible")
        return None

    monkeypatch.setattr(modulo, "call_command", revienta)
    with pytest.raises(RuntimeError):
        call_command("preparar", "--si-cambio", verbosity=0)

    assert not ParametroSistema.objects.filter(clave=modulo.Command.CLAVE_HUELLA).exists()


@pytest.mark.django_db
def test_si_cambio_aplica_una_migracion_pendiente_aunque_la_siembra_siga_igual(
    settings, monkeypatch
):
    """
    Una migración nueva no cambia la huella de siembra, pero sin aplicarla la
    tabla no existe y la pantalla que la usa revienta. Decidir solo por la
    huella dejaría ese caso fuera.
    """
    from apps.core.management.commands import preparar as modulo

    settings.DEBUG = True
    call_command("preparar", "--si-cambio", verbosity=0)

    monkeypatch.setattr(modulo.Command, "_hay_migraciones_pendientes", lambda self: True)
    llamadas = []
    monkeypatch.setattr(modulo, "call_command", lambda *a, **k: llamadas.append(a[0]))
    call_command("preparar", "--si-cambio", verbosity=0)
    assert "migrate" in llamadas
