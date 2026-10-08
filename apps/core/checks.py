"""
Comprobaciones de despliegue ejecutables.

Una lista en prosa se lee una vez y se olvida; estos checks corren en cada
`manage.py check --deploy` y en el CI. Se activan solo con DEBUG=False, que es
lo más parecido a "esto es producción" que el código puede saber.

    python manage.py check --deploy --fail-level WARNING
"""

from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Warning, register

ETIQUETA = "sibu"

# Hosts que solo tienen sentido en la máquina del desarrollador.
HOSTS_DE_DESARROLLO = frozenset(
    {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1", "testserver"}  # nosec B104  # noqa: S104
)


def _es_produccion() -> bool:
    return not settings.DEBUG


@register(ETIQUETA, deploy=True)
def comprobar_secretos(app_configs, **kwargs):
    problemas = []
    if not _es_produccion():
        return problemas

    clave = getattr(settings, "SECRET_KEY", "")
    if len(clave) < 50:
        problemas.append(
            Error(
                "SECRET_KEY es demasiado corta para producción.",
                hint=(
                    "Genere una de 50+ caracteres con "
                    "secrets.token_urlsafe(64) y póngala en el entorno."
                ),
                id="sibu.E001",
            )
        )
    # "dev-insecure-change-me" es el valor por omisión de base.py: se nombra
    # aquí para que el mensaje diga qué pasó y no solo que la clave es corta.
    if clave.startswith(("django-insecure", "dev-insecure", "v", "cambiar", "changeme")):
        problemas.append(
            Error(
                "SECRET_KEY parece un valor de desarrollo.",
                hint="Defina SECRET_KEY en el entorno; no la deje en el repositorio.",
                id="sibu.E002",
            )
        )
    hosts = getattr(settings, "ALLOWED_HOSTS", [])
    if "*" in hosts:
        problemas.append(
            Error(
                "ALLOWED_HOSTS contiene '*': acepta peticiones de cualquier dominio.",
                hint="Liste los dominios reales: sibu.unl.edu.ec",
                id="sibu.E003",
            )
        )
    elif not hosts:
        problemas.append(
            Error(
                "ALLOWED_HOSTS está vacío: Django rechazará todas las peticiones.",
                hint="Defina ALLOWED_HOSTS en el entorno, p. ej. sibu.unl.edu.ec",
                id="sibu.E004",
            )
        )
    elif all(h in HOSTS_DE_DESARROLLO for h in hosts):
        # Un valor heredado del entorno de desarrollo pasa las comprobaciones
        # anteriores y es igual de fatal: Django responde 400 a todo el que
        # entre por el dominio real. Arranca, el check calla, y nadie puede
        # usarlo. No se prohíbe localhost (una comprobación de salud local lo
        # necesita); se exige que no sea lo único.
        problemas.append(
            Error(
                "ALLOWED_HOSTS solo contiene hosts de desarrollo "
                f"({', '.join(hosts)}): nadie podrá entrar por el dominio real.",
                hint="Añada el dominio institucional, p. ej. sibu.unl.edu.ec",
                id="sibu.E005",
            )
        )
    return problemas


@register(ETIQUETA, deploy=True)
def comprobar_base_de_datos(app_configs, **kwargs):
    problemas = []
    if not _es_produccion():
        return problemas

    motor = settings.DATABASES.get("default", {}).get("ENGINE", "")
    if "sqlite" in motor:
        problemas.append(
            Error(
                "La base de datos de producción es SQLite.",
                hint="SIBU usa PostgreSQL 16: defina DATABASE_URL apuntando a Postgres.",
                id="sibu.E010",
            )
        )
    return problemas


@register(ETIQUETA, deploy=True)
def comprobar_proxy_y_csrf(app_configs, **kwargs):
    """
    Detrás de un proxy con HTTPS, Django rechaza los POST si no se declaran los
    orígenes de confianza. Es el fallo de despliegue más común y se manifiesta
    como "CSRF verification failed" en formularios que funcionaban en local.
    """
    problemas = []
    if not _es_produccion():
        return problemas

    origenes = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
    if getattr(settings, "SECURE_SSL_REDIRECT", False) and not origenes:
        problemas.append(
            Error(
                "Falta CSRF_TRUSTED_ORIGINS y el sitio fuerza HTTPS.",
                hint="Defina CSRF_TRUSTED_ORIGINS=https://sibu.unl.edu.ec o los POST fallarán.",
                id="sibu.E020",
            )
        )
        return problemas

    # Un origen sin esquema Django lo rechaza al arrancar en versiones nuevas y,
    # peor, se escribe así por costumbre: «sibu.unl.edu.ec» en vez de
    # «https://sibu.unl.edu.ec».
    sin_esquema = [o for o in origenes if "://" not in o]
    if sin_esquema:
        problemas.append(
            Error(
                f"CSRF_TRUSTED_ORIGINS sin esquema: {', '.join(sin_esquema)}.",
                hint="Debe llevar https://, no solo el dominio.",
                id="sibu.E021",
            )
        )

    # El fallo que de verdad muerde el día del despliegue: los orígenes no
    # cubren a los hosts. El sitio arranca, TODAS las páginas responden 200 y
    # nadie puede iniciar sesión, porque el 403 solo aparece al enviar el primer
    # formulario. Comprobado montando el despliegue completo: con
    # CSRF_TRUSTED_ORIGINS mal puesto, el login devuelve «Forbidden (Referer
    # checking failed)» y el resto del sistema parece sano.
    #
    # Se compara el host con su puerto, porque Django también lo compara: un
    # origen sin el puerto no vale para un sitio servido en un puerto no
    # estándar.
    hosts_cubiertos = set()
    for origen in origenes:
        autoridad = origen.split("://", 1)[-1].rstrip("/")
        hosts_cubiertos.add(autoridad)
        hosts_cubiertos.add(autoridad.split(":", 1)[0])

    def _cubierto(host: str) -> bool:
        if host in hosts_cubiertos:
            return True
        # `.dominio.ec` en ALLOWED_HOSTS es un comodín de subdominios; en los
        # orígenes se escribe `https://*.dominio.ec`.
        return any(
            host.lstrip(".") == cubierto.lstrip("*.").lstrip(".") for cubierto in hosts_cubiertos
        )

    huerfanos = [
        h
        for h in getattr(settings, "ALLOWED_HOSTS", [])
        if h not in ("*",) and h not in HOSTS_DE_DESARROLLO and not _cubierto(h)
    ]
    if huerfanos:
        problemas.append(
            Error(
                f"Estos hosts no tienen su origen en CSRF_TRUSTED_ORIGINS: "
                f"{', '.join(huerfanos)}. Las páginas se abrirán y NADIE podrá "
                "iniciar sesión: el 403 solo aparece al enviar un formulario.",
                hint="Añada https://<host> por cada uno, con el puerto si no es el 443.",
                id="sibu.E022",
            )
        )
    return problemas


@register(ETIQUETA, deploy=True)
def comprobar_almacenamiento(app_configs, **kwargs):
    problemas = []
    if not _es_produccion():
        return problemas

    media = str(getattr(settings, "MEDIA_ROOT", "") or "")
    if not media:
        problemas.append(
            Error("MEDIA_ROOT no está definido: no hay dónde archivar evidencias.", id="sibu.E030")
        )
    # El literal es el patrón que se busca, no una ruta que se use.
    elif media.startswith("/tmp"):  # nosec B108
        problemas.append(
            Error(
                "MEDIA_ROOT apunta a /tmp: las evidencias se perderían al reiniciar.",
                hint="Use un volumen persistente con copias de seguridad.",
                id="sibu.E031",
            )
        )
    elif not Path(media).exists():
        problemas.append(Warning(f"MEDIA_ROOT ({media}) no existe todavía.", id="sibu.W032"))
    return problemas


@register(ETIQUETA, deploy=True)
def comprobar_correo(app_configs, **kwargs):
    """
    El portal vincula cuentas enviando un código al correo institucional. Sin
    SMTP, nadie puede vincularse: el portal queda inservible en silencio.
    """
    problemas = []
    if not _es_produccion():
        return problemas

    backend = getattr(settings, "EMAIL_BACKEND", "")
    if "smtp" not in backend:
        problemas.append(
            Warning(
                "EMAIL_BACKEND no es SMTP: la vinculación del portal no podrá enviar códigos.",
                hint="Configure el SMTP institucional o el portal quedará inservible.",
                id="sibu.W040",
            )
        )
    elif not getattr(settings, "EMAIL_HOST", ""):
        problemas.append(Error("EMAIL_HOST vacío con backend SMTP.", id="sibu.E041"))
    return problemas


@register(ETIQUETA, deploy=True)
def comprobar_firma(app_configs, **kwargs):
    """La firma es opcional; pero si se activa, tiene que estar completa."""
    problemas = []
    proveedor = getattr(settings, "FIRMA_PROVIDER", "deshabilitada")
    if proveedor != "firmaec":
        return problemas

    faltan = [
        c
        for c in (
            "FIRMAEC_SERVICIO_URL",
            "FIRMAEC_SISTEMA",
            "FIRMAEC_API_KEY",
            "FIRMAEC_CALLBACK_API_KEY",
        )
        if not getattr(settings, c, "")
    ]
    if faltan:
        problemas.append(
            Error(
                f"FIRMA_PROVIDER='firmaec' pero falta configurar: {', '.join(faltan)}.",
                hint="O complete la configuración, o use FIRMA_PROVIDER=deshabilitada.",
                id="sibu.E050",
            )
        )
    if getattr(settings, "FIRMAEC_API_KEY", "") and getattr(
        settings, "FIRMAEC_API_KEY", ""
    ) == getattr(settings, "FIRMAEC_CALLBACK_API_KEY", ""):
        problemas.append(
            Error(
                "FIRMAEC_API_KEY y FIRMAEC_CALLBACK_API_KEY son iguales.",
                hint="Son credenciales de sentidos opuestos: si se filtra una, se filtran ambas.",
                id="sibu.E051",
            )
        )
    if not str(getattr(settings, "FIRMAEC_SERVICIO_URL", "")).startswith("https://"):
        problemas.append(Error("FIRMAEC_SERVICIO_URL debe usar https.", id="sibu.E052"))
    return problemas


@register(ETIQUETA, deploy=True)
def comprobar_confidencialidad(app_configs, **kwargs):
    """
    Aviso deliberado: no es un error, es una decisión que debe ser consciente.

    Con FIRMAEC_DESCENTRALIZADO_PROPIO=True, los informes de Psicología pueden
    salir hacia el firmador. Solo es correcto si ese servicio corre en
    infraestructura de la propia UNL.
    """
    problemas = []
    if getattr(settings, "FIRMAEC_DESCENTRALIZADO_PROPIO", False):
        problemas.append(
            Warning(
                "FIRMAEC_DESCENTRALIZADO_PROPIO=True: el contenido de Psicología "
                "puede salir hacia el firmador.",
                hint="Correcto SOLO si FirmaEC corre en infraestructura de la UNL. "
                "Si apunta al servicio centralizado del MINTEL, póngalo en False.",
                id="sibu.W060",
            )
        )
    return problemas


@register(ETIQUETA, deploy=True)
def comprobar_talleres(app_configs, **kwargs):
    problemas = []
    if getattr(settings, "TALLERES_ALMACEN", "local") != "gdrive":
        return problemas
    cfg = getattr(settings, "GOOGLE_OAUTH", {})
    if not cfg.get("CLIENT_SECRETS_FILE") or not cfg.get("SHARED_DRIVE_ID"):
        problemas.append(
            Error(
                "TALLERES_ALMACEN='gdrive' sin credenciales de Google Workspace.",
                hint="O complete GOOGLE_CLIENT_SECRETS y GOOGLE_SHARED_DRIVE_ID, o use 'local'.",
                id="sibu.E070",
            )
        )
    return problemas
