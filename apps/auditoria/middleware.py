"""
Middleware de auditoría: adjunta el usuario e IP de la petición a un contexto
por hilo para que las señales de los modelos registren autoría. El registro
efectivo de cada evento se implementa vía señales por modelo (signals.py).
"""

import threading

_local = threading.local()


def get_auditoria_context():
    """
    El contexto de la petición en curso, creado si no existe.

    Devolver un `{}` nuevo en cada llamada —como hacía antes— convierte
    cualquier escritura en él en un descarte silencioso: quien apuntaba algo lo
    apuntaba en un diccionario que nadie volvía a mirar.
    """
    if not hasattr(_local, "context"):
        _local.context = {}
    return _local.context


class AuditoriaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.context = {
            # Marca de que hay una petición en curso, y por tanto una
            # transacción envolviéndola: es lo que decide si un rechazo se
            # difiere al middleware o se escribe en el acto.
            "en_peticion": True,
            "usuario": getattr(request, "user", None),
            "ip": request.META.get("REMOTE_ADDR"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
        }
        try:
            respuesta = self.get_response(request)
        finally:
            # Aquí la vista ya terminó y, si abortó, su transacción ya se
            # revirtió: `ATOMIC_REQUESTS` envuelve la vista, no el middleware.
            # Este es el único punto desde el que un intento RECHAZADO puede
            # dejar rastro; escribirlo dentro de la vista lo borraría el
            # rollback que provoca el propio PermissionDenied.
            try:
                from .registro import volcar_rechazos

                volcar_rechazos()
            except Exception:  # noqa: BLE001
                # Auditar no puede tumbar la petición: un fallo al escribir el
                # registro no debe convertir un 403 legítimo en un 500.
                pass
            _local.context = {}
        return respuesta
