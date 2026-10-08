"""
Recuerda con qué usuario entrar.

La pregunta «¿y con qué usuario inicio sesión?» aparecía cada vez que se
levantaba el entorno, y la única respuesta estaba en la salida de `datos_demo`,
que ya se había perdido varias pantallas más arriba de la terminal.

    python manage.py cuentas        # o:  make cuentas

Lista las cuentas existentes con su rol y sus servicios. Las contraseñas solo
se muestran para las cuentas de demostración, que son ficticias y de clave
conocida; de las demás no se puede mostrar nada, porque están cifradas —y si se
pudieran mostrar, este comando sería el problema, no la ayuda—.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.usuarios.models import Usuario


class Command(BaseCommand):
    help = "Muestra las cuentas disponibles para iniciar sesión."

    def handle(self, *args, **opciones):
        from .datos_demo import ADMIN, CLAVE

        usuarios = (
            Usuario.objects.exclude(username="AnonymousUser")
            .select_related("perfil")
            .prefetch_related("perfil__servicios")
            .order_by("rol_principal", "username")
        )
        if not usuarios:
            self.stdout.write(
                self.style.WARNING("No hay ninguna cuenta creada: nadie puede iniciar sesión.")
            )
            self.stdout.write("Cree las de prueba con: python manage.py preparar")
            return

        self.stdout.write("")
        self.stdout.write(f"  {'usuario':<26} {'rol':<24} servicios")
        self.stdout.write("  " + "-" * 76)
        for usuario in usuarios:
            perfil = getattr(usuario, "perfil", None)
            servicios = (
                ", ".join(s.nombre for s in perfil.servicios.all()) if perfil else ""
            ) or "—"
            self.stdout.write(
                f"  {usuario.username:<26} {usuario.get_rol_principal_display():<24} {servicios}"
            )

        if not settings.DEBUG:
            # Con DEBUG=False la base no es de demostración: anunciar unas
            # contraseñas conocidas ahí sería una invitación a probarlas.
            self.stdout.write("")
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("  Contraseñas de las cuentas de demostración:"))
        self.stdout.write(f"    {ADMIN['username']:<26} {ADMIN['clave']}")
        self.stdout.write(f"    {'las demás':<26} {CLAVE}")
        self.stdout.write("")
        self.stdout.write("  Si una cuenta no está en esa siembra, su contraseña no se puede")
        self.stdout.write("  mostrar: está cifrada. Hay dos salidas:")
        self.stdout.write(
            "    make demo                       recrea las de prueba con clave conocida"
        )
        self.stdout.write(
            "    manage.py changepassword <usuario>   cambia la de una cuenta concreta"
        )
        self.stdout.write("")
