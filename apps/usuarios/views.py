"""
Ficha propia del profesional.

Cada profesional mantiene aquí lo que le identifica al atender y al firmar:
título, registro profesional, cédula y —desde hoy— fecha de nacimiento,
denominación del cargo y las actividades esenciales de su manual de puestos.
Antes solo se podía cargar desde el panel de administración, así que en la
práctica quedaba vacío.

Lo que NO se edita aquí son los servicios, la sección y el rol: de ellos
depende el RBAC, y una pantalla que los dejara tocar sería una vía para
ampliarse el acceso a uno mismo. Se muestran, en solo lectura, para que el
profesional pueda comprobar con qué permisos trabaja.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import Seccion, Servicio

from . import rbac
from .models import ActividadEsencial, PerfilProfesional, Rol, Usuario
from .rbac import SERVICIOS_CONFIDENCIALES
from .selectors import cuentas_sin_perfil, perfiles_para_gestion
from .services import (
    CAMPOS_CUENTA,
    CAMPOS_PERFIL,
    actualizar_mi_perfil,
    agregar_actividad,
    asignar_perfil,
    crear_perfil,
    eliminar_actividad,
)


def _mi_perfil_o_404(request):
    """El PerfilProfesional del usuario en sesión, o 404 si no tiene."""
    return get_object_or_404(PerfilProfesional, usuario=request.user)


@login_required
def mi_perfil(request):
    if request.method == "POST":
        accion = request.POST.get("accion", "actualizar")
        try:
            if accion == "actualizar":
                datos = {c: request.POST.get(c, "") for c in CAMPOS_CUENTA + CAMPOS_PERFIL}
                actualizar_mi_perfil(request.user, datos)
                messages.success(request, "Sus datos quedaron actualizados.")

            elif accion == "agregar_actividad":
                perfil = _mi_perfil_o_404(request)
                agregar_actividad(perfil, request.POST.get("descripcion", ""))
                messages.success(request, "Actividad agregada.")

            elif accion == "agregar_subactividad":
                perfil = _mi_perfil_o_404(request)
                superior = get_object_or_404(
                    ActividadEsencial, pk=request.POST.get("actividad_superior"), perfil=perfil
                )
                agregar_actividad(
                    perfil, request.POST.get("descripcion", ""), actividad_superior=superior
                )
                messages.success(request, "Sub-actividad agregada.")

            elif accion == "eliminar_actividad":
                perfil = _mi_perfil_o_404(request)
                actividad = get_object_or_404(
                    ActividadEsencial, pk=request.POST.get("actividad"), perfil=perfil
                )
                eliminar_actividad(actividad)
                messages.success(request, "Actividad eliminada.")

        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("usuarios:mi_perfil")

    perfil = (
        PerfilProfesional.objects.filter(usuario=request.user)
        .select_related("seccion")
        .prefetch_related("servicios")
        .first()
    )
    # Solo de primer nivel: cada una trae sus `subactividades` prefetched, en
    # el orden que ya fija `Meta.ordering` del modelo.
    actividades = (
        ActividadEsencial.objects.filter(perfil=perfil, actividad_superior=None)
        .prefetch_related("subactividades")
        .order_by("orden")
        if perfil
        else []
    )
    return render(
        request,
        "usuarios/mi_perfil.html",
        {
            "perfil": perfil,
            "servicios": perfil.servicios.all() if perfil else [],
            "actividades": actividades,
        },
    )


# ============================================================
# Gestión de perfiles (solo Administración General)
# ============================================================


def _solo_administracion(request) -> None:
    """
    Asignar servicios es conceder acceso, y el de Psicología abre contenido
    sellado. Lo decide Administración General y nadie más: ni la Dirección, ni
    la Coordinación, ni quien ya atiende en el servicio.
    """
    if not rbac.es_admin(request.user):
        raise PermissionDenied("La gestión de perfiles es de Administración General.")


@login_required
def gestion_perfiles(request):
    """
    Quién atiende, en qué servicio, con qué rol y si tiene horario.

    Hasta ahora esta pregunta solo se contestaba a mano desde `/admin/` de
    Django, que lista cuentas y perfiles por separado y no dice ni los
    servicios ni si hay franjas. La columna del horario es la que evita el
    desconcierto más común: un profesional bien dado de alta y sin franjas
    **no admite ninguna cita**, y nada en su ficha lo advertía.

    Las cuentas sin perfil van abajo a propósito: son las que no aparecen en
    ninguna bandeja, y la pregunta «¿por qué no sale Fulano?» se contesta aquí.
    """
    _solo_administracion(request)
    return render(
        request,
        "usuarios/gestion_perfiles.html",
        {
            "perfiles": perfiles_para_gestion(
                request.GET.get("q", ""), request.GET.get("seccion") or None
            ),
            "sin_perfil": cuentas_sin_perfil(),
            "secciones": Seccion.objects.order_by("nombre"),
            "q": request.GET.get("q", ""),
            "seccion": request.GET.get("seccion", ""),
            "confidenciales": SERVICIOS_CONFIDENCIALES,
        },
    )


@login_required
def editar_perfil(request, pk):
    """Sección, servicios, rol y firma digital de un profesional."""
    _solo_administracion(request)
    perfil = get_object_or_404(
        PerfilProfesional.objects.select_related("usuario", "seccion"), pk=pk
    )

    if request.method == "POST":
        try:
            asignar_perfil(
                perfil=perfil,
                seccion=Seccion.objects.filter(pk=request.POST.get("seccion") or 0).first(),
                servicios=Servicio.objects.filter(pk__in=request.POST.getlist("servicios")),
                rol_principal=request.POST.get("rol") or None,
                puede_firmar_digital=request.POST.get("firma") == "1",
                usuario_que_asigna=request.user,
            )
            messages.success(request, f"Perfil de {perfil.usuario.get_full_name()} actualizado.")
            return redirect("usuarios:gestion_perfiles")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

    return render(
        request,
        "usuarios/editar_perfil.html",
        {
            "perfil": perfil,
            "secciones": Seccion.objects.order_by("nombre"),
            "servicios": Servicio.objects.filter(activo=True).order_by("nombre"),
            "mis_servicios": {s.pk for s in perfil.servicios.all()},
            "roles": Rol.choices,
            "confidenciales": SERVICIOS_CONFIDENCIALES,
            "franjas": perfil.agendas.filter(activa=True).count(),
        },
    )


@login_required
@require_POST
def alta_perfil(request, pk):
    """
    Convierte una cuenta en alguien que atiende.

    Solo por POST: crea una ficha, y una vista que escribe no puede responder a
    un GET —bastaría un `<img src="...">` ajeno para dar de alta a alguien—.

    Sin perfil una cuenta no sale en ninguna bandeja, no admite cita y no puede
    tener horario: crear el perfil es lo que la pone a atender, así que va por
    el mismo camino auditado que una asignación.
    """
    _solo_administracion(request)
    usuario = get_object_or_404(Usuario, pk=pk)
    try:
        perfil = crear_perfil(usuario=usuario, usuario_que_asigna=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("usuarios:gestion_perfiles")
    messages.success(
        request,
        f"{usuario.get_full_name() or usuario.username} ya tiene ficha profesional. "
        "Asígnele sección y servicios para que pueda atender.",
    )
    return redirect("usuarios:editar_perfil", pk=perfil.pk)
