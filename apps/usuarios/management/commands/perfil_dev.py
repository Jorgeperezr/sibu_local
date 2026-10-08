"""
Da a una cuenta un PerfilProfesional con acceso a todos los servicios, para
recorrer el sistema en desarrollo.

Reemplaza el bloque de shell que había que pegar a mano (y que fallaba al
adivinar nombres de campo: PerfilProfesional no tiene 'cedula' — la cédula vive
en Persona, no en el perfil del profesional).

    python manage.py perfil_dev                 # sobre el superusuario, si hay uno solo
    python manage.py perfil_dev --usuario jorgeperez

ADVERTENCIA: el perfil resultante ve los NUEVE servicios, Psicología incluida.
Eso rompe el sello de confidencialidad a propósito, para poder navegar. NUNCA
lo use en producción: allí cada profesional lleva únicamente su servicio. Por
eso el comando se niega a ejecutarse si DEBUG=False.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Seccion, Servicio
from apps.usuarios.models import PerfilProfesional, Rol, Usuario


class Command(BaseCommand):
    help = "Asigna un PerfilProfesional de desarrollo con acceso a todos los servicios."

    def add_arguments(self, parser):
        parser.add_argument(
            "--usuario",
            dest="usuario",
            default=None,
            help="username de la cuenta. Si se omite, usa el único superusuario existente.",
        )
        parser.add_argument(
            "--rol",
            dest="rol",
            default=Rol.ADMIN_GENERAL,
            choices=[r.value for r in Rol],
            help="Rol principal a asignar (por defecto admin_general).",
        )

    def handle(self, *args, **opciones):
        # La negativa en producción no es decorativa: este perfil viola el
        # sello de Psicología. Que exista el comando no debe ser una puerta
        # trasera en el servidor real.
        if not settings.DEBUG:
            raise CommandError(
                "perfil_dev solo corre con DEBUG=True. En producción, cada "
                "profesional recibe únicamente su servicio, por ventanilla de "
                "administración."
            )

        usuario = self._resolver_usuario(opciones["usuario"])

        usuario.rol_principal = opciones["rol"]
        usuario.save(update_fields=["rol_principal"])

        seccion = Seccion.objects.filter(codigo="salud").first() or Seccion.objects.first()
        perfil, creado = PerfilProfesional.objects.get_or_create(
            usuario=usuario,
            defaults={"seccion": seccion, "titulo": "Perfil de desarrollo"},
        )
        todos = Servicio.objects.all()
        perfil.servicios.set(todos)

        verbo = "creado" if creado else "actualizado"
        self.stdout.write(
            self.style.SUCCESS(
                f"Perfil {verbo} para '{usuario.username}': rol={usuario.rol_principal}, "
                f"{todos.count()} servicios asignados."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Este perfil ve Psicología: úselo solo para navegar en desarrollo, "
                "nunca en producción."
            )
        )

    def _resolver_usuario(self, username):
        if username:
            try:
                return Usuario.objects.get(username=username)
            except Usuario.DoesNotExist as exc:
                raise CommandError(f"No existe el usuario '{username}'.") from exc

        superusuarios = Usuario.objects.filter(is_superuser=True)
        n = superusuarios.count()
        if n == 0:
            raise CommandError(
                "No hay superusuarios. Cree uno con 'createsuperuser' o pase --usuario."
            )
        if n > 1:
            nombres = ", ".join(superusuarios.values_list("username", flat=True))
            raise CommandError(f"Hay varios superusuarios ({nombres}). Indique cuál con --usuario.")
        return superusuarios.first()
