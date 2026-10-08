"""
Carga los datos base de SIBU: secciones, servicios y grupos de rol,
según la estructura organizacional del informe (secciones 3 y 10).

Uso:  python manage.py seed_inicial
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.core.models import Seccion, Servicio
from apps.usuarios.models import Rol

# Estructura: sección -> [(servicio, permite_talleres_por_defecto)]
ESTRUCTURA = {
    "Sección Salud": [
        ("Medicina", False),
        ("Enfermería", False),
        ("Odontología", False),
        ("Laboratorio Clínico", False),
        ("Farmacia", False),
    ],
    "Sección Psicopedagógica": [
        ("Psicología", True),
        ("Psicopedagogía", True),
    ],
    "Sección Trabajo Social": [
        ("Trabajo Social", True),
    ],
    "Sección Becas": [
        ("Becas y Ayudas Económicas", False),
    ],
}


class Command(BaseCommand):
    help = "Crea secciones, servicios y grupos de rol iniciales."

    def handle(self, *args, **options):
        for nombre_seccion, servicios in ESTRUCTURA.items():
            seccion, _ = Seccion.objects.get_or_create(
                codigo=slugify(nombre_seccion), defaults={"nombre": nombre_seccion}
            )
            for nombre_servicio, talleres in servicios:
                Servicio.objects.get_or_create(
                    codigo=slugify(nombre_servicio),
                    defaults={
                        "nombre": nombre_servicio,
                        "seccion": seccion,
                        "permite_talleres": talleres,
                    },
                )
        self.stdout.write(self.style.SUCCESS("Secciones y servicios creados."))

        for _value, label in Rol.choices:
            Group.objects.get_or_create(name=label)
        self.stdout.write(self.style.SUCCESS("Grupos de rol creados."))
        self.stdout.write(self.style.SUCCESS("Seed inicial completado."))
