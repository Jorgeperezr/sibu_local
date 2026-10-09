"""
Tareas Celery del módulo de citas: recordatorios T-48h y T-24h (informe 5.2 M17).

La creación de la notificación NO vive aquí: está en `services.crear_recordatorio`,
y de ahí la toman tanto este task como el comando `recordatorios`, que es el que
usa la portable. Dos copias del mismo texto acabarían diciendo cosas distintas
en la misma bandeja.
"""

from celery import shared_task

from .selectors import citas_para_recordatorio
from .services import crear_recordatorio


@shared_task
def enviar_recordatorios(horas: int = 24, tolerancia_minutos: int | None = None) -> int:
    """Crea notificaciones para cada cita próxima a `horas` horas."""
    citas = citas_para_recordatorio(horas, tolerancia_minutos=tolerancia_minutos)
    return sum(1 for cita in citas if crear_recordatorio(cita, horas))
