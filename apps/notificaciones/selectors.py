"""Consultas de la bandeja de notificaciones."""

from .models import Notificacion

# Tipos que no pueden pasar desapercibidos en una lista larga.
URGENTES = {"resultado_critico", "riesgo_psicologia"}


def mias(usuario, *, solo_sin_leer: bool = False):
    """
    Las notificaciones de este usuario, las urgentes primero.

    Parte del usuario de la sesión y nunca de un id de la URL: es la misma
    regla del portal —aislar por identidad, no por rol—, y aquí importa igual,
    porque el título de una notificación de Psicología ya dice de qué servicio
    es su destinatario.
    """
    consulta = Notificacion.objects.filter(usuario=usuario)
    if solo_sin_leer:
        consulta = consulta.exclude(estado=Notificacion.Estado.LEIDA)
    return consulta.order_by("-creado_en")


def es_urgente(notificacion) -> bool:
    return notificacion.tipo in URGENTES
