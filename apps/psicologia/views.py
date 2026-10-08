"""
Interfaz web de Psicología.

TODAS las vistas verifican el acceso con `verificar_acceso_atencion`, que para
Psicología deniega a cualquiera que no sea del servicio. `@login_required` por
sí solo NO basta: dejaría abrir la ficha de cualquier paciente cambiando el id
en la URL.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import CIE10, Servicio
from apps.core.selectors import diagnosticos_por_servicio
from apps.expediente.models import Expediente
from apps.medicina.models import Diagnostico
from apps.medicina.services import agregar_diagnostico
from apps.usuarios.decorators import verificar_acceso_atencion, verificar_es_del_servicio

from . import services
from .models import EscalaPsicometrica, FichaPsicologica


@login_required
def bandeja(request):
    """Procesos activos del servicio de Psicología."""
    servicio = get_object_or_404(Servicio, codigo="psicologia")
    verificar_es_del_servicio(request.user, servicio)

    fichas = (
        FichaPsicologica.objects.filter(
            atencion__servicio=servicio, estado_proceso=FichaPsicologica.Estado.ACTIVO
        )
        .select_related("atencion__expediente__persona", "atencion__profesional__usuario")
        .order_by("-atencion__fecha_hora")
    )
    return render(
        request,
        "psicologia/bandeja.html",
        {"fichas": fichas, "riesgo_alto": FichaPsicologica.Riesgo.ALTO},
    )


@login_required
def iniciar(request, expediente_id):
    """Abre un proceso psicológico."""
    servicio = get_object_or_404(Servicio, codigo="psicologia")
    verificar_es_del_servicio(request.user, servicio)
    expediente = get_object_or_404(Expediente, pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        raise PermissionDenied("Su usuario no tiene perfil profesional.")

    try:
        ficha = services.crear_ficha(
            expediente=expediente,
            profesional=perfil,
            motivo=request.POST.get("motivo", "Consulta psicológica"),
            usuario=request.user,
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        activo = services.proceso_activo(expediente)
        if activo:
            return redirect("psicologia:proceso", pk=activo.pk)
        return redirect("expediente:detalle", pk=expediente_id)
    return redirect("psicologia:proceso", pk=ficha.pk)


@login_required
def proceso(request, pk):
    """Ficha, sesiones y escalas del proceso."""
    ficha = get_object_or_404(
        FichaPsicologica.objects.select_related(
            "atencion__expediente__persona", "atencion__servicio"
        ),
        pk=pk,
    )
    verificar_acceso_atencion(request.user, ficha.atencion)
    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "sesion":
                services.registrar_sesion(
                    ficha,
                    profesional=perfil,
                    evolucion=request.POST.get("evolucion", ""),
                    temas=request.POST.get("temas", ""),
                    tecnicas=request.POST.get("tecnicas", ""),
                    tareas=request.POST.get("tareas", ""),
                    proxima_sesion=request.POST.get("proxima_sesion") or None,
                )
                messages.success(request, "Sesión registrada.")
            elif accion == "escala":
                aplicacion = services.aplicar_escala(
                    ficha,
                    request.POST["escala"],
                    int(request.POST["puntaje"]),
                    aplicado_por=perfil,
                )
                if aplicacion.alerta:
                    messages.warning(
                        request,
                        f"{aplicacion.escala}: {aplicacion.interpretacion}. "
                        f"El riesgo se elevó a ALTO y se notificó al coordinador.",
                    )
                else:
                    messages.success(request, f"{aplicacion.escala}: {aplicacion.interpretacion}.")
            elif accion == "diagnostico":
                agregar_diagnostico(
                    ficha.atencion,
                    request.POST["cie10"],
                    tipo=request.POST.get("tipo", Diagnostico.TipoDx.PRESUNTIVO),
                    principal=request.POST.get("principal") == "on",
                )
                messages.success(request, "Diagnóstico agregado.")
            elif accion == "riesgo":
                services.marcar_riesgo(ficha, request.POST["nivel"], request.POST.get("nota", ""))
                messages.success(request, "Nivel de riesgo actualizado.")
            elif accion == "ficha":
                for campo in (
                    "historia_problema",
                    "impresion_diagnostica",
                    "plan_terapeutico",
                    "modalidad",
                ):
                    if campo in request.POST:
                        setattr(ficha, campo, request.POST[campo])
                ficha.save()
                messages.success(request, "Ficha actualizada.")
            elif accion == "cerrar":
                services.cerrar_proceso(ficha, request.POST["estado"])
                messages.success(request, "Proceso cerrado.")
                return redirect("psicologia:bandeja")
        except (ValidationError, KeyError, ValueError) as exc:
            detalle = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            messages.error(request, detalle)
        except EscalaPsicometrica.DoesNotExist:
            messages.error(request, "La escala indicada no existe o está inactiva.")
        except CIE10.DoesNotExist:
            messages.error(request, "Código CIE-10 no encontrado.")
        return redirect("psicologia:proceso", pk=pk)

    return render(
        request,
        "psicologia/proceso.html",
        {
            "ficha": ficha,
            "sesiones": ficha.sesiones.select_related("profesional__usuario"),
            "escalas_aplicadas": ficha.escalas.all(),
            "catalogo": EscalaPsicometrica.objects.filter(activo=True),
            "niveles": FichaPsicologica.Riesgo.choices,
            "modalidades": FichaPsicologica.Modalidad.choices,
            "estados_cierre": [
                (FichaPsicologica.Estado.ALTA, "Alta"),
                (FichaPsicologica.Estado.ABANDONO, "Abandono"),
                (FichaPsicologica.Estado.DERIVADO, "Derivado a externo"),
            ],
            "es_alto": ficha.riesgo_nivel == FichaPsicologica.Riesgo.ALTO,
            "diagnosticos": Diagnostico.objects.filter(atencion=ficha.atencion).select_related(
                "cie10"
            ),
            "cie10_disponibles": diagnosticos_por_servicio("psicologia"),
            "tipos_dx": Diagnostico.TipoDx.choices,
        },
    )
