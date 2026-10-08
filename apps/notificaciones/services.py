"""
Marcar notificaciones como leídas.

El módulo existía como un comentario. Las notificaciones se escribían desde seis
sitios y no había forma de leerlas ni de darlas por vistas.
"""

from django.utils import timezone

from .models import Notificacion


def marcar_leida(notificacion: Notificacion, usuario) -> Notificacion:
    """
    Da una notificación por vista, anotando cuándo.

    Idempotente y sin reescribir la hora: la PRIMERA lectura es la que cuenta.
    Sobre un valor crítico, volver a abrir la bandeja tres días después no puede
    mover el momento en que alguien se enteró.
    """
    if notificacion.usuario_id != getattr(usuario, "pk", None):
        raise PermissionError("Una notificación solo la lee su destinatario.")
    if notificacion.estado == Notificacion.Estado.LEIDA:
        return notificacion
    notificacion.estado = Notificacion.Estado.LEIDA
    notificacion.leida_en = timezone.now()
    notificacion.save(update_fields=["estado", "leida_en", "actualizado_en"])
    return notificacion


def marcar_todas_leidas(usuario) -> int:
    """Las pendientes de este usuario, y solo las suyas. Devuelve cuántas."""
    pendientes = Notificacion.objects.filter(usuario=usuario).exclude(
        estado=Notificacion.Estado.LEIDA
    )
    return pendientes.update(estado=Notificacion.Estado.LEIDA, leida_en=timezone.now())


def sin_leer(usuario) -> int:
    """Cuántas le quedan por ver. Lo consulta el contador de la cabecera."""
    if not getattr(usuario, "is_authenticated", False):
        return 0
    return (
        Notificacion.objects.filter(usuario=usuario)
        .exclude(estado=Notificacion.Estado.LEIDA)
        .count()
    )
