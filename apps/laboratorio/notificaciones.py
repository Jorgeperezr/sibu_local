"""
Notificaciones de laboratorio (informe 5.2 M17, 12.4).

Al publicar una orden:
1. Se notifica al profesional solicitante (in-app).
2. Se envía el informe al correo institucional del paciente.
3. Si hay valores críticos, se genera una alerta inmediata destacada.
"""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.notificaciones.models import Notificacion

from .models import OrdenLaboratorio, ResultadoParametro


def _resultados_de(orden: OrdenLaboratorio):
    return (
        ResultadoParametro.objects.filter(orden_examen__orden=orden)
        .select_related("parametro", "orden_examen__examen")
        .order_by("orden_examen__examen__nombre", "parametro__orden")
    )


def notificar_publicacion(orden: OrdenLaboratorio, *, enviar_correo: bool = True) -> dict:
    """Dispara todas las notificaciones de una orden publicada."""
    resumen = {"solicitante": False, "paciente": False, "criticos": 0}

    # 1. Notificar al profesional solicitante
    solicitante = orden.atencion.profesional
    Notificacion.objects.create(
        usuario=solicitante.usuario,
        tipo="resultado_laboratorio",
        titulo=f"Resultados disponibles — orden #{orden.pk}",
        mensaje=(
            f"Los resultados de laboratorio de "
            f"{orden.atencion.expediente.persona.nombre_completo} "
            f"ya están publicados."
        ),
        canal=Notificacion.Canal.IN_APP,
        referencia_tipo="OrdenLaboratorio",
        referencia_id=orden.pk,
    )
    resumen["solicitante"] = True

    # 2. Alerta destacada por valores críticos
    criticos = _resultados_de(orden).filter(marcador=ResultadoParametro.Marcador.CRITICO)
    if criticos.exists():
        detalle = ", ".join(f"{r.parametro.nombre}={r.valor}" for r in criticos)
        Notificacion.objects.create(
            usuario=solicitante.usuario,
            tipo="resultado_critico",
            titulo=f"⚠ VALOR CRÍTICO — orden #{orden.pk}",
            mensaje=(
                f"Paciente {orden.atencion.expediente.persona.nombre_completo}: {detalle}. "
                f"Requiere atención inmediata."
            ),
            canal=Notificacion.Canal.IN_APP,
            referencia_tipo="OrdenLaboratorio",
            referencia_id=orden.pk,
        )
        resumen["criticos"] = criticos.count()

    # 3. Enviar al correo institucional del paciente
    if enviar_correo:
        resumen["paciente"] = enviar_resultados_al_paciente(orden)

    return resumen


def enviar_resultados_al_paciente(orden: OrdenLaboratorio) -> bool:
    """
    Envía el informe de resultados al correo institucional del paciente.

    Devuelve True si se envió. Si la persona no tiene correo institucional
    registrado, no se envía (y queda constancia en la notificación in-app).
    """
    persona = orden.atencion.expediente.persona
    correo = persona.correo_institucional
    if not correo:
        Notificacion.objects.create(
            tipo="resultado_sin_correo",
            titulo=f"Resultados sin enviar — orden #{orden.pk}",
            mensaje=(
                f"{persona.nombre_completo} no tiene correo institucional registrado. "
                f"Los resultados deben entregarse en ventanilla."
            ),
            canal=Notificacion.Canal.IN_APP,
            destinatario_nombre=persona.nombre_completo,
            referencia_tipo="OrdenLaboratorio",
            referencia_id=orden.pk,
        )
        return False

    contexto = {
        "persona": persona,
        "orden": orden,
        "resultados": _resultados_de(orden),
        "unidad": "Unidad de Bienestar Universitario — UNL",
    }
    cuerpo = render_to_string("laboratorio/correo_resultados.txt", contexto)

    send_mail(
        subject=f"Resultados de laboratorio — Orden #{orden.pk}",
        message=cuerpo,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "bienestar@unl.edu.ec"),
        recipient_list=[correo],
        fail_silently=False,
    )

    Notificacion.objects.create(
        tipo="resultado_enviado",
        titulo=f"Resultados enviados — orden #{orden.pk}",
        mensaje=f"Informe enviado a {correo}.",
        canal=Notificacion.Canal.EMAIL,
        destinatario_correo=correo,
        destinatario_nombre=persona.nombre_completo,
        estado=Notificacion.Estado.ENVIADA,
        referencia_tipo="OrdenLaboratorio",
        referencia_id=orden.pk,
    )

    orden.enviado_correo_paciente = True
    orden.save(update_fields=["enviado_correo_paciente", "actualizado_en"])
    return True
