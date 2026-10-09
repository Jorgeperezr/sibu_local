"""Interfaz web de Psicopedagogía: ficha, seguimientos e impacto."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import PeriodoAcademico, Servicio
from apps.expediente.models import Expediente
from apps.expediente.services import borrador_abierto, exigir_atencion_editable
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


# Solo POST: abrir una atención CREA la historia clínica, y una vista que
# escribe no puede responder a un GET. Bastaría un `<img
# src="/psicopedagogia/iniciar/37/">` en cualquier página que abriera un profesional
# para dejar una historia a su nombre sobre alguien a quien no ha visto. El
# expediente la abre con un formulario.
@require_POST
@login_required
def iniciar(request, expediente_id):
    servicio = get_object_or_404(Servicio, codigo="psicopedagogia")
    verificar_es_del_servicio(request.user, servicio)
    expediente = get_object_or_404(Expediente, pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        raise PermissionDenied("Su usuario no tiene perfil profesional.")

    # Si este profesional ya tiene un borrador abierto con esta persona, se
    # continúa ese. Antes se creaba una atención NUEVA en cada entrada: pulsar
    # la acción, volver atrás y volver a pulsar dejaba dos fichas en blanco en
    # el expediente de la misma persona, y una ficha clínica no se borra.
    abierto = borrador_abierto(expediente, servicio, perfil, "psicopedagogia")
    if abierto is not None:
        return redirect("psicopedagogia:ficha", pk=abierto.pk)

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
            exigir_atencion_editable(obj.atencion)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("psicopedagogia:ficha", pk=obj.pk)

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
