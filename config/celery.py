"""Configuración de Celery para tareas asíncronas (cargas, notificaciones, reportes)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("sibu")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
