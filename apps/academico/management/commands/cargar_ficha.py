"""Esqueleto del comando de carga (se implementa en Sprint 1)."""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Carga la ficha socioeconómica (esqueleto — implementado en Sprint 1)."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str)
        parser.add_argument("--periodo", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        raise CommandError("Implementación pendiente (esqueleto inicial).")
