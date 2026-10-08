"""Interfaz web de Becas (fase 1)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import PeriodoAcademico, Servicio
from apps.usuarios.decorators import verificar_es_del_servicio

from . import services
from .models import BecaBeneficiario, SeguimientoBeca


def _servicio():
    return Servicio.objects.get(codigo="becas-y-ayudas-economicas")


@login_required
def bandeja(request):
    verificar_es_del_servicio(request.user, _servicio())
    periodo = PeriodoAcademico.objects.filter(vigente=True).first()
    contexto = {"periodo": periodo, "beneficiarios": [], "resumen": []}
    if periodo:
        contexto["beneficiarios"] = services.beneficiarios_vigentes(periodo)
        contexto["resumen"] = services.resumen_por_tipo(periodo)
    return render(request, "becas/bandeja.html", contexto)


@login_required
def ficha(request, pk):
    verificar_es_del_servicio(request.user, _servicio())
    beneficiario = get_object_or_404(
        BecaBeneficiario.objects.select_related("expediente__persona", "tipo_beca"), pk=pk
    )
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        raise PermissionDenied("Su usuario no tiene perfil profesional.")

    if request.method == "POST":
        periodo = PeriodoAcademico.objects.filter(vigente=True).first()
        accion = request.POST.get("accion")
        try:
            if accion == "verificar" and periodo:
                seg = services.verificar_matricula(beneficiario, periodo, perfil)
                if seg.matricula_vigente is True:
                    messages.success(request, "Matrícula vigente confirmada.")
                elif seg.matricula_vigente is False:
                    messages.warning(
                        request,
                        "El dato institucional no muestra matrícula vigente. "
                        "Revise antes de suspender: la beca no se suspende sola.",
                    )
                else:
                    messages.info(request, seg.detalle)
            elif accion == "seguimiento" and periodo:
                services.registrar_seguimiento(
                    beneficiario,
                    periodo=periodo,
                    tipo=request.POST["tipo"],
                    detalle=request.POST.get("detalle", ""),
                    profesional=perfil,
                )
                messages.success(request, "Seguimiento registrado.")
            elif accion == "estado":
                services.cambiar_estado(
                    beneficiario,
                    request.POST["estado"],
                    causal=request.POST.get("causal", ""),
                    usuario=request.user,
                )
                messages.success(request, "Estado actualizado.")
        except (ValidationError, KeyError) as exc:
            detalle = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            messages.error(request, detalle)
        return redirect("becas:ficha", pk=pk)

    return render(
        request,
        "becas/ficha.html",
        {
            "b": beneficiario,
            "seguimientos": beneficiario.seguimientos.select_related("periodo"),
            "tipos_seguimiento": SeguimientoBeca.Tipo.choices,
            "estados": BecaBeneficiario.Estado.choices,
        },
    )
