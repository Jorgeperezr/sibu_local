"""
Consultas de lectura de Trabajo Social.

La bandeja del servicio: qué expedientes tienen ficha socioeconómica y en qué
estado están. Trabajo Social era el único de los nueve servicios sin bandeja
—se llegaba a una ficha solo desde el expediente de otro módulo—, así que no
había ninguna pantalla que respondiera «¿cuáles son mis casos?».
"""

from __future__ import annotations

from django.db.models import Q

from .models import FichaSocioeconomica

# Con menos de tres letras la búsqueda devuelve el padrón entero: no es una
# búsqueda, es un volcado. Mismo criterio que en el expediente.
MINIMO_TEXTO = 3

# El orden en que la Unidad prioriza. `calcular_puntaje` produce exactamente
# estas cuatro cadenas; que la lista viva aquí y no en la plantilla evita que
# un cambio en los tramos deje el filtro ofreciendo estratos inexistentes.
ESTRATOS = [
    "Extrema vulnerabilidad",
    "Vulnerabilidad alta",
    "Vulnerabilidad media",
    "Sin vulnerabilidad económica",
]

# Una ficha pre-poblada desde matrícula todavía no tiene estrato: nadie la ha
# verificado. Faltaba en el resumen, y era el único tramo con casos dentro: la
# pantalla enseñaba cuatro ceros sobre siete fichas pendientes, que se lee como
# «no hay nada que hacer» cuando es exactamente lo contrario. Es la cola de
# trabajo del servicio, así que va primero.
#
# El valor tiene que ser distinto de la cadena vacía, que en el filtro significa
# «todos los estratos»; en la base ese estrato SÍ es la cadena vacía, y la
# traducción entre las dos cosas vive en `casos`.
SIN_VERIFICAR = "sin verificar"
ESTRATOS_DEL_FILTRO = [SIN_VERIFICAR, *ESTRATOS]


def casos(texto: str = "", estrato: str = ""):
    """
    Las fichas vigentes, la más recientemente tocada primero.

    Solo las vigentes: el historial de versiones se consulta dentro de cada
    ficha, y mezclarlo aquí haría aparecer a la misma persona varias veces con
    puntajes distintos, que es justo lo que no debe pasar en una bandeja.

    No revela qué otro servicio atiende a la persona: eso delataría un paso por
    un servicio confidencial.
    """
    consulta = (
        FichaSocioeconomica.objects.filter(vigente=True)
        .select_related("expediente__persona")
        .order_by("-actualizado_en")
    )
    if estrato == SIN_VERIFICAR:
        consulta = consulta.filter(Q(estrato="") | Q(estrato__isnull=True))
    elif estrato:
        consulta = consulta.filter(estrato=estrato)

    texto = (texto or "").strip()
    if len(texto) >= MINIMO_TEXTO:
        for palabra in texto.split():
            consulta = consulta.filter(
                Q(expediente__persona__nombres__icontains=palabra)
                | Q(expediente__persona__apellidos__icontains=palabra)
                | Q(expediente__persona__cedula__icontains=palabra)
            )
    return consulta


def resumen_por_estrato() -> list[dict]:
    """
    Cuántas fichas vigentes hay en cada estrato, en el orden de prioridad.

    Se incluyen los estratos con cero: un tramo ausente de la tabla se lee como
    «no lo hemos mirado», y uno con cero, como «no hay ninguno». No es lo mismo.

    Y se incluye «sin verificar», que faltaba. Sin él la pantalla enseñaba
    cuatro ceros mientras la tabla de abajo listaba siete fichas: los cuatro
    tramos son los que produce `calcular_puntaje`, y una ficha pre-poblada
    desde matrícula todavía no ha pasado por ahí. Un resumen que suma cero
    sobre una bandeja llena no resume: contradice.
    """
    from django.db.models import Count

    conteos = dict(
        FichaSocioeconomica.objects.filter(vigente=True)
        .values_list("estrato")
        .annotate(n=Count("id"))
    )
    sin_verificar = conteos.get("", 0) + conteos.get(None, 0)
    return [{"estrato": SIN_VERIFICAR, "total": sin_verificar}] + [
        {"estrato": e, "total": conteos.get(e, 0)} for e in ESTRATOS
    ]
