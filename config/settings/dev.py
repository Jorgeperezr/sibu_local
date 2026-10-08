"""Ajustes de desarrollo (Codespaces / macOS Intel). Nunca usar en producción."""

import os

from .base import *  # noqa
from .base import BASE_DIR, env  # explícito: evita la ambigüedad del star-import
from .clave_dev import clave_de_desarrollo
from .origenes_dev import origenes_confiables

DEBUG = True
ALLOWED_HOSTS = ["*"]  # Codespaces asigna hosts dinámicos


SECRET_KEY = env("SECRET_KEY", default="") or clave_de_desarrollo(BASE_DIR)

INSTALLED_APPS += ["debug_toolbar", "django_extensions"]  # noqa
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa
INTERNAL_IPS = ["127.0.0.1"]

# Correo por consola en desarrollo (no se envía nada real)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CSRF. Se lee del entorno y se completa con lo inevitable: el dominio que
# Codespaces asigna al puerto y, sobre todo, `https://localhost:8000`, que es el
# Origin que presenta su reenvío de puertos aunque el navegador muestre otro.
CSRF_TRUSTED_ORIGINS = origenes_confiables(os.environ)

# Cuando aun así falle, que la pantalla diga qué Origin llegó, cuáles se
# aceptan y qué hacer. La de Django dice «does not match any trusted origins» y
# ahí termina. Solo en desarrollo: en producción no se le enseña la
# configuración a quien no debería verla.
CSRF_FAILURE_VIEW = "apps.core.csrf.vista_fallo_csrf"

# En desarrollo se relajan controles que solo aplican tras HTTPS
AXES_ENABLED = env.bool("AXES_ENABLED", default=False)  # noqa
