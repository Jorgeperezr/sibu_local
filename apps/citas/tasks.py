"""
Tareas Celery del módulo de citas: recordatorios T-48h y T-24h (informe 5.2 M17).
"""

from celery import shared_task

from apps.notificaciones.models import Notificacion

from .selectors import citas_para_recordatorio


@shared_task
def enviar_recordatorios(horas: int = 24, tolerancia_minutos: int | None = None) -> int:
    """Crea notificaciones para cada cita próxima a `horas` horas."""
    citas = citas_para_recordatorio(horas, tolerancia_minutos=tolerancia_minutos)
    creadas = 0
    for cita in citas:
        persona = cita.expediente.persona
        if Notificacion.objects.filter(
            tipo=f"recordatorio_cita_{horas}h",
            referencia_tipo="Cita",
            referencia_id=cita.id,
        ).exists():
            continue
        Notificacion.objects.create(
            # Si el paciente tiene cuenta del portal verificada, esa es su
            # identidad dentro del sistema y el aviso va ahí. Sin `usuario`, un
            # recordatorio con canal IN_APP —el caso de quien no tiene correo
            # institucional— quedaba dirigido a ningún usuario de la
            # aplicación: no salía por correo ni aparecía en ninguna bandeja.
            usuario=_cuenta_del_portal(cita.expediente),
            tipo=f"recordatorio_cita_{horas}h",
            titulo=f"Recordatorio de cita en {horas}h",
            mensaje=(
                f"Estimado/a {persona.nombre_completo}: recordamos su cita "
                f"en {cita.servicio.nombre} el "
                f"{cita.fecha_hora:%d/%m/%Y a las %H:%M}."
            ),
            canal=(
                Notificacion.Canal.EMAIL
                if persona.correo_institucional
                else Notificacion.Canal.IN_APP
            ),
            destinatario_correo=persona.correo_institucional,
            destinatario_nombre=persona.nombre_completo,
            referencia_tipo="Cita",
            referencia_id=cita.id,
        )
        creadas += 1
    return creadas


def _cuenta_del_portal(expediente):
    """La cuenta del portal vinculada y verificada de este expediente, si la hay."""
    vinculacion = getattr(expediente, "vinculacion_portal", None)
    if vinculacion is None or not vinculacion.verificado:
        return None
    return vinculacion.usuario
