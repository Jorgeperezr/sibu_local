from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Núcleo"

    def ready(self):
        from . import (
            checks,  # noqa: F401  registra los checks de despliegue
            signals,  # noqa: F401
        )
