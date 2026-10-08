"""Ajustes de pruebas: base de datos rápida y sin migraciones costosas."""

from .base import *  # noqa

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
AXES_ENABLED = False
CELERY_TASK_ALWAYS_EAGER = True
