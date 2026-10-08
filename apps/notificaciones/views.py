"""Bandeja de notificaciones del usuario."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import selectors, services
from .models import Notificacion


@login_required
def bandeja(request):
    """Lo que el sistema le avisó a este usuario, lo urgente marcado."""
    solo_sin_leer = request.GET.get("filtro") == "sin_leer"
    notificaciones = list(selectors.mias(request.user, solo_sin_leer=solo_sin_leer)[:200])
    return render(
        request,
        "notificaciones/bandeja.html",
        {
            "notificaciones": notificaciones,
            "urgentes": {n.pk for n in notificaciones if selectors.es_urgente(n)},
            "solo_sin_leer": solo_sin_leer,
            "sin_leer": services.sin_leer(request.user),
        },
    )


@require_POST
@login_required
def leer(request, pk):
    """
    Marca una como vista.

    `get_object_or_404` filtrando por el usuario de la sesión: la de otro no
    existe para esta vista, así que cambiar el id devuelve 404 y no 403 —no
    hace falta confirmar que existe—.
    """
    notificacion = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    services.marcar_leida(notificacion, request.user)
    return redirect(request.META.get("HTTP_REFERER") or "notificaciones:bandeja")


@require_POST
@login_required
def leer_todas(request):
    cuantas = services.marcar_todas_leidas(request.user)
    if cuantas:
        messages.success(request, f"{cuantas} notificación(es) marcadas como leídas.")
    return redirect("notificaciones:bandeja")
