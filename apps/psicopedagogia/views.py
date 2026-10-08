"""Interfaz web de Psicopedagogía: ficha, seguimientos e impacto."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import PeriodoAcademico, Servicio
from apps.expediente.models import Expediente
from apps.usuarios.decorators import verificar_acceso_atencion, verificar_es_del_servicio

from . import services
from .models import FichaPsicopedagogica


@login_required
def bandeja(request):
    servicio = get_object_or_404(Servicio, codigo="psicopedagogia")
    verificar_es_del_servicio(request.user, servicio)
    fichas = (
        FichaPsicopedagogica.objects.filter(atencion__servicio=servicio)
        .select_related("atencion__expediente__persona")
        .order_by("-atencion__fecha_hora")
    )
    return render(request, "psicopedagogia/bandeja.html", {"fichas": fichas})


@login_required
def iniciar(request, expediente_id):
    servicio = get_object_or_404(Servicio, codigo="psicopedagogia")
    verificar_es_del_servicio(request.user, servicio)
    expediente = get_object_or_404(Expediente, pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        raise PermissionDenied("Su usuario no tiene perfil profesional.")
    ficha = services.crear_ficha(
        expediente=expediente,
        profesional=perfil,
        motivo=request.POST.get("motivo", "Apoyo psicopedagógico"),
        usuario=request.user,
    )
    return redirect("psicopedagogia:ficha", pk=ficha.pk)


@login_required
def ficha(request, pk):
    obj = get_object_or_404(
        FichaPsicopedagogica.objects.select_related(
            "atencion__expediente__persona", "atencion__servicio"
        ),
        pk=pk,
    )
    verificar_acceso_atencion(request.user, obj.atencion)

    if request.method == "POST":
        try:
            if request.POST.get("accion") == "seguimiento":
                services.registrar_seguimiento(
                    obj,
                    request.POST["periodo"],
                    promedio_antes=request.POST.get("promedio_antes") or None,
                    promedio_despues=request.POST.get("promedio_despues") or None,
                    observaciones=request.POST.get("observaciones", ""),
                )
                messages.success(request, "Seguimiento registrado.")
            else:
                obj.plan_intervencion = request.POST.get("plan_intervencion", "")
                obj.save(update_fields=["plan_intervencion"])
                messages.success(request, "Plan actualizado.")
        except (ValidationError, KeyError) as exc:
            detalle = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            messages.error(request, detalle)
        return redirect("psicopedagogia:ficha", pk=pk)

    return render(
        request,
        "psicopedagogia/ficha.html",
        {
            "ficha": obj,
            "seguimientos": obj.seguimientos.all(),
            "impacto": services.impacto(obj),
            "periodos": PeriodoAcademico.objects.order_by("-fecha_inicio")[:8],
        },
    )
