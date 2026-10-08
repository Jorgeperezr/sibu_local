"""
Interfaz web de Derivaciones: bandeja de entrada y cierre del ciclo.

La bandeja muestra las derivaciones dirigidas al servicio del usuario. El
retorno de un servicio confidencial ya viene saneado desde services, así que
mostrarlo aquí no filtra nada.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import Servicio
from apps.expediente.models import Atencion, Expediente
from apps.usuarios import rbac
from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES, servicios_del_usuario

from . import services
from .models import Derivacion


@login_required
def bandeja(request):
    """Derivaciones recibidas por los servicios del usuario."""
    mis_servicios = servicios_del_usuario(request.user)
    if not mis_servicios:
        raise PermissionDenied("Su usuario no tiene servicios asignados.")

    servicio_id = request.GET.get("servicio") or next(iter(mis_servicios))
    if int(servicio_id) not in mis_servicios:
        raise PermissionDenied("Ese servicio no le corresponde.")
    servicio = get_object_or_404(Servicio, pk=servicio_id)

    return render(
        request,
        "derivaciones/bandeja.html",
        {
            "servicio": servicio,
            "servicios": Servicio.objects.filter(pk__in=mis_servicios),
            "entrantes": services.bandeja_entrada(servicio),
            "emitidas": Derivacion.objects.filter(atencion_origen__servicio=servicio)
            .select_related("servicio_destino", "atencion_origen__expediente__persona")
            .order_by("-creado_en")[:20],
            "confidenciales": SERVICIOS_CONFIDENCIALES,
        },
    )


@login_required
def derivar(request, atencion_id):
    """Emite una derivación desde una atención."""
    atencion = get_object_or_404(
        Atencion.objects.select_related("servicio", "expediente__persona"), pk=atencion_id
    )
    if atencion.servicio_id not in servicios_del_usuario(request.user):
        raise PermissionDenied("No puede derivar desde un servicio que no es suyo.")

    if request.method == "POST":
        try:
            destino = get_object_or_404(Servicio, pk=request.POST["servicio_destino"])
            services.derivar(
                atencion,
                destino,
                motivo=request.POST.get("motivo", ""),
                resumen=request.POST.get("resumen", ""),
                prioridad=request.POST.get("prioridad", "normal"),
                usuario=request.user,
            )
            messages.success(request, f"Derivación enviada a {destino.nombre}.")
            return redirect("expediente:detalle", pk=atencion.expediente_id)
        except (ValidationError, KeyError) as exc:
            detalle = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            messages.error(request, detalle)

    # Los destinos con una derivación viva se apartan del desplegable: ofrecerlos
    # solo servía para que `services.derivar` los rechazara después.
    abiertas = services.destinos_con_derivacion_abierta(atencion.expediente)
    disponibles = (
        Servicio.objects.filter(activo=True)
        .exclude(pk=atencion.servicio_id)
        .exclude(pk__in=abiertas)
    )
    return render(
        request,
        "derivaciones/derivar.html",
        {
            "atencion": atencion,
            "servicios": disponibles,
            "abiertas": sorted(abiertas.values()),
        },
    )


@login_required
def gestionar(request, pk):
    """Acepta, rechaza, agenda, atiende o retorna una derivación."""
    derivacion = get_object_or_404(
        Derivacion.objects.select_related(
            "servicio_destino", "atencion_origen__expediente__persona"
        ),
        pk=pk,
    )
    mis_servicios = servicios_del_usuario(request.user)
    if (
        derivacion.servicio_destino_id not in mis_servicios
        and derivacion.atencion_origen.servicio_id not in mis_servicios
    ):
        raise PermissionDenied("Esta derivación no le corresponde.")

    accion = request.POST.get("accion")
    try:
        if accion == "aceptar":
            services.aceptar(derivacion)
            messages.success(request, "Derivación aceptada.")
        elif accion == "rechazar":
            services.rechazar(derivacion, request.POST.get("motivo", ""))
            messages.success(request, "Derivación rechazada.")
        elif accion == "agendar":
            services.marcar_agendada(derivacion)
            messages.success(request, "Marcada como agendada.")
        elif accion == "atender":
            atencion = get_object_or_404(Atencion, pk=request.POST["atencion_destino"])
            services.atender(derivacion, atencion)
            messages.success(request, "Derivación vinculada a la atención.")
        elif accion == "retornar":
            services.retornar(derivacion, request.POST.get("texto", ""))
            if derivacion.servicio_destino.codigo in SERVICIOS_CONFIDENCIALES:
                messages.info(
                    request,
                    "Retorno enviado como acuse: por confidencialidad del servicio no "
                    "se transmite el contenido clínico a quien derivó.",
                )
            else:
                messages.success(request, "Retorno enviado.")
    except (ValidationError, KeyError) as exc:
        detalle = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        messages.error(request, detalle)
    return redirect("derivaciones:bandeja")


@login_required
def trazabilidad(request, expediente_id):
    """
    Recorrido del paciente entre servicios.

    Llevaba solo `@login_required`, igual que las nueve vistas que el Sprint 7b
    corrigió: cualquier autenticado —un estudiante incluido— cambiaba el id del
    expediente y leía a qué servicios fue esa persona y por qué.
    """
    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("No tiene permisos para consultar expedientes.")
    expediente = get_object_or_404(Expediente.objects.select_related("persona"), pk=expediente_id)
    return render(
        request,
        "derivaciones/trazabilidad.html",
        {
            "expediente": expediente,
            "traza": services.trazabilidad(expediente, request.user),
        },
    )
