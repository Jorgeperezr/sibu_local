"""
Registro de accesos al contenido clínico.

`LogAuditoria.Accion` definía `READ` desde el primer sprint y se usaba en un
solo sitio, así que abrir la historia clínica de alguien no dejaba constancia.
Contra el abuso interno, impedir el acceso es media defensa; la otra mitad es
que quede escrito quién miró.

**El rechazo es el caso delicado.** `verificar_acceso_atencion` lanza
`PermissionDenied`, y con `ATOMIC_REQUESTS = True` toda la petición es una
transacción: un log escrito dentro de la vista se va con el rollback y el
intento fallido no deja rastro. Es la trampa que CLAUDE.md señala —«auditar y
abortar no caben en la misma transacción»— y que ya costó dos veces.

La salida es no escribirlo ahí: el rechazo se apunta en la petición y lo
escribe el middleware, que corre FUERA del bloque atómico de la vista. Lo que
sí se permite se escribe en el momento, porque su transacción sí va a
confirmarse.
"""

from apps.auditoria.middleware import get_auditoria_context


def _contexto():
    ctx = get_auditoria_context()
    return {"ip": ctx.get("ip"), "user_agent": ctx.get("user_agent", "")}


def _datos(usuario, atencion, resultado):
    from apps.auditoria.models import LogAuditoria

    return {
        "usuario": usuario if getattr(usuario, "pk", None) else None,
        "rol_activo": getattr(usuario, "rol_principal", "") or "",
        "accion": LogAuditoria.Accion.READ,
        "modulo": atencion.servicio.codigo,
        "entidad": "Atencion",
        "entidad_id": str(atencion.pk),
        "expediente_id": atencion.expediente_id,
        "servicio": atencion.servicio.codigo,
        "resultado": resultado,
        **_contexto(),
    }


def registrar_lectura(usuario, atencion) -> None:
    """Un acceso concedido. Se escribe ya: su transacción va a confirmarse."""
    from apps.auditoria.models import LogAuditoria

    LogAuditoria.objects.create(**_datos(usuario, atencion, "ok"))


def anotar_rechazo(usuario, atencion) -> None:
    """
    Un acceso denegado. NO se escribe aquí.

    Lo que sigue a esta llamada es un `PermissionDenied` que aborta la
    transacción de la petición. Se deja apuntado en el contexto por hilo y lo
    escribe `AuditoriaMiddleware` cuando la vista ya terminó y el rollback ya
    ocurrió.
    """
    from apps.auditoria.models import LogAuditoria

    contexto = get_auditoria_context()
    datos = _datos(usuario, atencion, "denegado")
    if not contexto.get("en_peticion"):
        # Fuera de una petición —un comando, una tarea— no hay transacción de
        # `ATOMIC_REQUESTS` que revierta nada, así que diferirlo solo serviría
        # para que nadie lo escribiera nunca.
        LogAuditoria.objects.create(**datos)
        return
    contexto.setdefault("rechazos", []).append(datos)


def volcar_rechazos() -> int:
    """
    Escribe los rechazos apuntados durante la petición. Lo llama el middleware.

    Devuelve cuántos escribió, que es lo que permite comprobarlo sin mirar la
    base desde la propia prueba del middleware.
    """
    from apps.auditoria.models import LogAuditoria

    pendientes = get_auditoria_context().get("rechazos") or []
    if not pendientes:
        return 0
    cuantos = len(pendientes)
    LogAuditoria.objects.bulk_create([LogAuditoria(**datos) for datos in pendientes])
    pendientes.clear()
    return cuantos
