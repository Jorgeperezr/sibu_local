"""
Consultas de la bitácora, con el sello aplicado a la propia bitácora.

Una línea que diga «jorge.perez leyó la atención 47 del expediente de María
Pérez, servicio Psicología» filtra por la puerta de atrás justo lo que el sello
protege: que esa persona es paciente de Psicología. Que el dato esté en una
pantalla de auditoría y no en una clínica no lo hace menos identificable.

La regla: **el actor siempre se ve; el paciente, no.** Quien audita ve que
alguien de Psicología hizo una lectura y cuándo —que es lo que hace falta para
pedir cuentas— sin ver de quién. El propio servicio ve sus entradas completas,
porque para él no hay nada que ocultar.
"""

from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES, servicios_del_usuario

# Columnas por las que se puede filtrar, y por dónde llegar a cada una. Lista
# blanca, igual que en el padrón: `filter()` acepta cualquier cadena, incluida
# la que recorra una relación hasta donde no debería llegarse.
FILTROS = {
    "usuario": "usuario_id",
    "accion": "accion",
    "resultado": "resultado",
    "servicio": "servicio",
    "modulo": "modulo",
}


def bitacora(usuario, *, filtros=None, desde=None, hasta=None):
    """
    Los registros que este usuario puede consultar, ya filtrados.

    Un profesional de un servicio confidencial ve SOLO los de su servicio: no
    es que se le oculte el resto, es que auditar es función de gobierno y no de
    atención. Quien gobierna ve todo, con lo sellado velado.
    """
    from .models import LogAuditoria

    consulta = LogAuditoria.objects.select_related("usuario").order_by("-fecha_hora")

    mis_servicios = _codigos_de_servicio(usuario)
    confidenciales_propios = mis_servicios & SERVICIOS_CONFIDENCIALES
    if not _puede_gobernar(usuario):
        # No gobierna: solo se audita a sí mismo y a su servicio.
        consulta = consulta.filter(servicio__in=confidenciales_propios or mis_servicios)

    for clave, valor in (filtros or {}).items():
        campo = FILTROS.get(clave)
        if campo and valor:
            consulta = consulta.filter(**{campo: valor})
    if desde:
        consulta = consulta.filter(fecha_hora__date__gte=desde)
    if hasta:
        consulta = consulta.filter(fecha_hora__date__lte=hasta)
    return consulta


def filas_para(usuario, registros):
    """
    Cada registro con lo que este usuario puede ver de él.

    `velado` dice que la identidad del paciente se retiró; `expediente` viene a
    `None` en ese caso. Se resuelve aquí y no en la plantilla porque una
    plantilla que reciba el expediente y decida no pintarlo lo lleva igualmente
    en el contexto, y basta un descuido para imprimirlo.
    """
    mis_servicios = _codigos_de_servicio(usuario)
    expedientes = _expedientes_de(registros)
    filas = []
    for registro in registros:
        velado = bool(
            registro.servicio
            and registro.servicio in SERVICIOS_CONFIDENCIALES
            and registro.servicio not in mis_servicios
        )
        filas.append(
            {
                "registro": registro,
                "velado": velado,
                "expediente": None if velado else expedientes.get(registro.expediente_id),
            }
        )
    return filas


def opciones_de_filtro(usuario):
    """Valores que existen en lo que este usuario puede ver, no todos los posibles."""
    from .models import LogAuditoria

    visibles = bitacora(usuario)
    return {
        "usuarios": sorted(
            {
                (r.usuario_id, r.usuario.get_full_name() or r.usuario.username)
                for r in visibles.exclude(usuario__isnull=True)[:500]
            },
            key=lambda par: par[1],
        ),
        "acciones": LogAuditoria.Accion.choices,
        "resultados": sorted(set(visibles.values_list("resultado", flat=True))),
    }


# ------------------------------------------------------------------ apoyo


def _puede_gobernar(usuario) -> bool:
    from apps.usuarios.models import Rol
    from apps.usuarios.rbac import es_admin

    return es_admin(usuario) or usuario.rol_principal in {Rol.DIRECTOR, Rol.COORDINADOR}


def _codigos_de_servicio(usuario) -> set[str]:
    from apps.core.models import Servicio

    ids = servicios_del_usuario(usuario)
    if not ids:
        return set()
    return set(Servicio.objects.filter(pk__in=ids).values_list("codigo", flat=True))


def _expedientes_de(registros) -> dict:
    """Los expedientes de una página de registros, en una consulta y no en N."""
    from apps.expediente.models import Expediente

    ids = {r.expediente_id for r in registros if r.expediente_id}
    if not ids:
        return {}
    return {e.pk: e for e in Expediente.objects.filter(pk__in=ids).select_related("persona")}
