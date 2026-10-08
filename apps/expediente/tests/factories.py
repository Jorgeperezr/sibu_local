"""Factories mínimas para pruebas del expediente y RBAC."""

from apps.core.models import Seccion, Servicio
from apps.expediente.models import Atencion, Expediente, Persona
from apps.usuarios.models import PerfilProfesional, Rol, Usuario


def crear_estructura():
    salud, _ = Seccion.objects.get_or_create(codigo="salud", defaults={"nombre": "Salud"})
    psico, _ = Seccion.objects.get_or_create(
        codigo="psicopedagogica", defaults={"nombre": "Psicopedagógica"}
    )
    medicina, _ = Servicio.objects.get_or_create(
        codigo="medicina", defaults={"nombre": "Medicina", "seccion": salud}
    )
    psicologia, _ = Servicio.objects.get_or_create(
        codigo="psicologia", defaults={"nombre": "Psicología", "seccion": psico}
    )
    return {"salud": salud, "psico": psico, "medicina": medicina, "psicologia": psicologia}


def crear_profesional(username, servicio, seccion, rol=Rol.PROFESIONAL):
    user = Usuario.objects.create_user(
        username=username,
        password="x",
        rol_principal=rol,
        first_name=username.title(),
        last_name="Prueba",
    )
    perfil = PerfilProfesional.objects.create(usuario=user, seccion=seccion)
    perfil.servicios.add(servicio)
    return user, perfil


def crear_expediente(cedula="1104567894"):
    persona = Persona.objects.create(
        cedula=cedula,
        nombres="Test",
        apellidos="Paciente",
        tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
    )
    return Expediente.objects.create(persona=persona, numero_expediente=f"EXP-{cedula}")


def crear_atencion(expediente, servicio, perfil):
    from django.utils import timezone

    return Atencion.objects.create(
        expediente=expediente,
        servicio=servicio,
        profesional=perfil,
        fecha_hora=timezone.now(),
        motivo_consulta="prueba",
    )
