"""Interfaz web de Talleres."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.usuarios.rbac import servicios_del_usuario

from . import services
from .models import Taller
from .providers import get_almacen


@login_required
def bandeja(request):
    mis_servicios = servicios_del_usuario(request.user)
    if not mis_servicios:
        # Un usuario del portal (o cualquiera sin servicios) no navega las
        # bandejas internas: 403 explícito, no una página vacía de un módulo
        # que no le corresponde.
        raise PermissionDenied("Su usuario no tiene servicios asignados.")
    talleres = (
        Taller.objects.filter(eliminado_en__isnull=True, servicio_id__in=mis_servicios)
        .select_related("servicio", "responsable__usuario")
        .order_by("-fecha")
    )
    return render(
        request,
        "talleres/bandeja.html",
        {"talleres": talleres, "cobertura": services.cobertura()},
    )


@login_required
def detalle(request, pk):
    taller = get_object_or_404(
        Taller.objects.select_related("servicio", "responsable__usuario"), pk=pk
    )
    if taller.servicio_id not in servicios_del_usuario(request.user):
        raise PermissionDenied("Este taller pertenece a otro servicio.")
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        raise PermissionDenied("Su usuario no tiene perfil profesional.")

    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "participante":
                p = services.registrar_participante(
                    taller,
                    cedula=request.POST.get("cedula", ""),
                    asistio=request.POST.get("asistio") == "on",
                )
                if p.validado:
                    messages.success(request, "Participante registrado y validado.")
                else:
                    messages.info(
                        request,
                        "Participante registrado. La cédula no corresponde a nadie "
                        "conocido por la institución: cuenta igual como asistente.",
                    )
            elif accion == "ejecutar":
                services.marcar_ejecutado(taller, usuario=request.user)
                messages.success(request, "Taller marcado como ejecutado.")
            elif accion == "evidencia":
                archivo = request.FILES.get("archivo")
                if archivo is None:
                    raise ValidationError("Seleccione un archivo.")
                services.adjuntar_evidencia(
                    taller,
                    nombre=archivo.name,
                    contenido=archivo.read(),
                    mime=archivo.content_type or "application/octet-stream",
                    usuario=request.user,
                )
                messages.success(request, "Evidencia archivada.")
            elif accion == "cerrar":
                services.cerrar_taller(taller, usuario=request.user)
                messages.success(request, "Taller cerrado.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("talleres:detalle", pk=pk)

    almacen = get_almacen()
    return render(
        request,
        "talleres/detalle.html",
        {
            "t": taller,
            "participantes": taller.participantes.select_related("expediente__persona"),
            "evidencias": taller.evidencias.filter(eliminado_en__isnull=True),
            "almacen": almacen,
            "almacen_disponible": almacen.disponible(),
            "motivo_almacen": "" if almacen.disponible() else almacen.motivo_no_disponible(),
        },
    )
