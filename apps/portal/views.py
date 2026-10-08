"""
Vistas del portal.

Regla única e innegociable: TODO parte de `services.expediente_de(request.user)`.
Ningún recurso se busca por un id de URL sin filtrar por el expediente propio.
El portal no reutiliza las vistas de profesionales ni su RBAC: su aislamiento
es por identidad, no por rol.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.usuarios.models import Rol

from . import services


def _requiere_portal(request):
    """Devuelve el expediente vinculado o corta la petición."""
    if request.user.rol_principal != Rol.USUARIO_FINAL:
        # Un profesional no navega el portal con su cuenta de trabajo: si
        # además es paciente, su acceso se gestiona por ventanilla. Mezclar
        # ambas sesiones confundiría qué rol hizo qué en la auditoría.
        raise PermissionDenied("El portal es para estudiantes y beneficiarios.")
    return services.expediente_de(request.user)


@login_required
def inicio(request):
    expediente = _requiere_portal(request)
    if expediente is None:
        return redirect("portal:vincular")
    return render(
        request,
        "portal/panel.html",
        {
            "persona": expediente.persona,
            "citas": services.mis_citas(expediente),
            "resultados": services.mis_resultados_publicados(expediente),
            "recetas": services.mis_recetas(expediente),
            "becas": services.mis_becas(expediente),
        },
    )


@login_required
def vincular(request):
    if request.user.rol_principal != Rol.USUARIO_FINAL:
        raise PermissionDenied("El portal es para estudiantes y beneficiarios.")
    if services.expediente_de(request.user) is not None:
        return redirect("portal:inicio")

    pendiente = (
        request.user.vinculacion_portal if hasattr(request.user, "vinculacion_portal") else None
    )
    if request.method == "POST":
        try:
            if request.POST.get("accion") == "confirmar":
                services.confirmar_vinculacion(request.user, request.POST.get("token", ""))
                messages.success(request, "Cuenta vinculada. Bienvenido.")
                return redirect("portal:inicio")
            v = services.solicitar_vinculacion(request.user, request.POST.get("cedula", ""))
            messages.info(
                request,
                f"Enviamos un código a {v.correo_destino}. Revise su correo institucional.",
            )
            return redirect("portal:vincular")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return render(request, "portal/vincular.html", {"pendiente": pendiente})


@login_required
def citas(request):
    """Agendar: servicio → profesional con agenda → turnos de los próximos 14 días."""
    from apps.citas import services as citas_services
    from apps.core.models import Servicio
    from apps.usuarios.models import PerfilProfesional

    expediente = _requiere_portal(request)
    if expediente is None:
        return redirect("portal:vincular")

    if request.method == "POST":
        try:
            if request.POST.get("accion") == "cancelar":
                services.cancelar_mi_cita(expediente, int(request.POST["cita_id"]), request.user)
                messages.success(request, "Cita cancelada.")
            else:
                from datetime import datetime

                profesional = get_object_or_404(PerfilProfesional, pk=request.POST["profesional"])
                servicio = get_object_or_404(Servicio, pk=request.POST["servicio"])
                fecha_hora = datetime.fromisoformat(request.POST["turno"])
                if timezone.is_naive(fecha_hora):
                    fecha_hora = timezone.make_aware(fecha_hora)
                services.agendar_cita(
                    expediente,
                    servicio=servicio,
                    profesional=profesional,
                    fecha_hora=fecha_hora,
                    usuario=request.user,
                )
                messages.success(request, "Cita agendada. Recibirá recordatorios.")
        except (ValidationError, KeyError, ValueError) as exc:
            detalle = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            messages.error(request, detalle)
        return redirect("portal:citas")

    servicio_id = request.GET.get("servicio")
    turnos, servicio_sel = [], None
    if servicio_id:
        servicio_sel = Servicio.objects.filter(pk=servicio_id, activo=True).first()
        if servicio_sel:
            hoy = timezone.localdate()
            profesionales = (
                PerfilProfesional.objects.filter(
                    agendas__servicio=servicio_sel, agendas__activa=True
                )
                .distinct()
                .select_related("usuario")
            )
            for prof in profesionales:
                for dias in range(1, 15):
                    fecha = hoy + timedelta(days=dias)
                    for turno in citas_services.turnos_disponibles(prof, servicio_sel, fecha):
                        turnos.append({"profesional": prof, "turno": turno})
            turnos.sort(key=lambda t: t["turno"])
            turnos = turnos[:40]

    return render(
        request,
        "portal/citas.html",
        {
            "citas": services.mis_citas(expediente),
            "servicios": Servicio.objects.filter(activo=True).order_by("nombre"),
            "servicio_sel": servicio_sel,
            "turnos": turnos,
        },
    )
