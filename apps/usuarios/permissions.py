"""Permisos DRF reutilizables para el RBAC de SIBU."""

from rest_framework.permissions import BasePermission

from .models import Rol


class EsProfesionalDelServicio(BasePermission):
    """Permite el acceso solo si el usuario tiene asignado el servicio del objeto."""

    def has_object_permission(self, request, view, obj):
        servicio = getattr(obj, "servicio_id", None)
        if servicio is None:
            return True
        perfil = getattr(request.user, "perfil", None)
        if perfil is None:
            return False
        return perfil.servicios.filter(pk=servicio).exists()


class EsAdministrador(BasePermission):
    """
    Administra la base institucional: por rol o por el permiso que lo dice.

    El permiso explícito existe porque hay una cuenta que necesita cargar la
    base Y ver contenido clínico, y el rol de administrador le quitaría lo
    segundo (`rbac.es_admin()` filtra las atenciones). La misma regla que
    aplica la vista web, para que la API y la pantalla no se contradigan.
    """

    def has_permission(self, request, view):
        usuario = request.user
        return usuario.is_authenticated and (
            usuario.is_superuser
            or usuario.rol_principal == Rol.ADMIN_GENERAL
            or usuario.has_perm("academico.add_cargainstitucional")
        )


class PuedeVerAtencion(BasePermission):
    """
    Aplica `rbac.puede_ver_atencion` al objeto de la petición.

    Defensa a nivel de objeto: complementa el filtrado de queryset. La API es
    una superficie nueva para el sello de Psicología, así que el control no
    puede depender solo de que el queryset esté bien filtrado.

    Acepta tanto una Atencion como cualquier objeto que tenga `.atencion`
    (FichaPsicologica, AtencionOdontologia, etc.).
    """

    def has_object_permission(self, request, view, obj):
        from apps.expediente.models import Atencion

        from . import rbac

        atencion = obj if isinstance(obj, Atencion) else getattr(obj, "atencion", None)
        if atencion is None:
            return True
        return rbac.puede_ver_atencion(request.user, atencion)


class EsDelServicio(BasePermission):
    """
    Permite el acceso solo a los profesionales de un servicio concreto.

    Se usa para endpoints que no cuelgan de una Atencion (por ejemplo la
    bandeja de derivaciones de un servicio).
    """

    codigo_servicio: str = ""

    def has_permission(self, request, view):
        from .rbac import servicios_del_usuario

        codigo = getattr(view, "codigo_servicio", self.codigo_servicio)
        if not codigo:
            return True
        from apps.core.models import Servicio

        servicio = Servicio.objects.filter(codigo=codigo).first()
        if servicio is None:
            return False
        return servicio.pk in servicios_del_usuario(request.user)


class EsPersonalDeLaUnidad(BasePermission):
    """
    Exige ser personal de la Unidad para llegar al endpoint.

    Es el par de escritura de `rbac.visible_para_personal`. Filtrar el queryset
    protege lo que se lee y el detalle por id, pero **no protege el `create`**:
    un POST no pasa por el queryset. Sin esto, la autorización nunca llegaba a
    correr y lo único que separaba a un estudiante de escribir en el sistema
    era que su carga fuera válida. Se comprobó que a veces lo era: llegó a
    concederse una beca y a crear la agenda de un profesional.

    Un 400 no es protección, es la validación diciendo que la autorización dejó
    pasar. Esto responde 403 antes.

    Deja fuera al rol USUARIO_FINAL —la cuenta de un estudiante—, que trabaja
    por el portal; y no estrecha más, porque quién puede escribir QUÉ es cosa
    de cada endpoint. Esto es el suelo.
    """

    def has_permission(self, request, view):
        from .rbac import puede_ver_expediente

        usuario = request.user
        return bool(usuario and usuario.is_authenticated and puede_ver_expediente(usuario))
