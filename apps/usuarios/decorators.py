"""
Control de acceso para vistas web.

Las vistas de plantilla no pasan por los permisos de DRF, así que necesitan su
propia comprobación. Sin esto, `@login_required` deja que cualquier usuario
autenticado abra la atención de cualquier paciente con solo cambiar el id de la
URL.
"""

from django.core.exceptions import PermissionDenied

from . import rbac


def verificar_acceso_atencion(user, atencion, break_glass: bool = False) -> None:
    """
    Lanza PermissionDenied (403) si el usuario no puede ver la atención.

    Se usa al principio de cada vista que muestra contenido clínico. Para
    Psicología, `rbac.puede_ver_atencion` deniega a todo el que no sea del
    servicio, incluso con break_glass.
    """
    from apps.auditoria import registro

    if not rbac.puede_ver_atencion(user, atencion, break_glass=break_glass):
        # No se escribe aquí: el PermissionDenied de la línea siguiente aborta
        # la transacción de la petición y se llevaría el registro por delante.
        # Lo escribe el middleware, ya fuera del bloque atómico.
        registro.anotar_rechazo(user, atencion)
        raise PermissionDenied(
            "No tiene acceso al contenido de este servicio. "
            "Si es un caso de emergencia, use el acceso justificado desde el expediente."
        )
    registro.registrar_lectura(user, atencion)


def verificar_es_del_servicio(user, servicio) -> None:
    """Lanza PermissionDenied si el usuario no pertenece al servicio."""
    if servicio.pk not in rbac.servicios_del_usuario(user):
        raise PermissionDenied(f"No pertenece al servicio {servicio.nombre}.")
