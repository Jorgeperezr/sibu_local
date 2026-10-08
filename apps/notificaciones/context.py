"""
El contador de notificaciones sin leer, disponible en todas las pantallas.

Una bandeja a la que hay que acordarse de entrar no sirve para avisar de un
valor crítico de laboratorio. El contador viaja en el contexto de cada página
para que aparezca sin buscarlo.

Es una consulta `COUNT` por página; cuando eso pese, la vía es cachearlo por
usuario e invalidarlo al crear o marcar una notificación, no quitar el aviso.
"""

from . import services


def notificaciones(request):
    usuario = getattr(request, "user", None)
    return {"notificaciones_sin_leer": services.sin_leer(usuario)}
