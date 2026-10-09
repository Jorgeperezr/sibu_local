"""
Crea los recordatorios de cita que ya tocaba enviar y nadie envió.

Existe porque el task de Celery no bastaba:

- El planificador configurado es el de base de datos (`django_celery_beat`) y
  el código no crea ninguna fila de `PeriodicTask`. El recordatorio T-48h/T-24h
  estaba escrito y probado, y no corría nunca.
- En una portable no hay demonio al que programarle nada.

Este comando es idempotente: la portable lo llama en cada arranque y en un
servidor va en una entrada de cron. Llamarlo dos veces seguidas no duplica
nada.

    python manage.py recordatorios
    python manage.py recordatorios --silencioso    # para el cron
"""

from django.core.management.base import BaseCommand

from apps.citas.services import recordatorios_pendientes


class Command(BaseCommand):
    help = "Crea los recordatorios de cita pendientes (T-48h y T-24h)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--silencioso",
            action="store_true",
            help="No escribir nada si no había nada que hacer.",
        )

    def handle(self, *args, **opciones):
        creados = recordatorios_pendientes()
        if creados:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{creados} recordatorio{'s' if creados != 1 else ''} de cita creado"
                    f"{'s' if creados != 1 else ''}."
                )
            )
        elif not opciones["silencioso"]:
            self.stdout.write("No había recordatorios pendientes.")
