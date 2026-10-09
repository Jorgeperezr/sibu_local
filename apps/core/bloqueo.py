"""
La pantalla que se ve tras demasiados intentos fallidos.

django-axes trae la suya: «Account locked: too many login attempts. Please try
again later.» En inglés, fuera de la línea gráfica y sin decir cuánto hay que
esperar, sobre un sistema que está entero en español.

En una portable eso es peor que un detalle de traducción: no hay
administrador a quien llamar. Quien se equivoca cinco veces se queda mirando
un error en otro idioma sin saber que basta con esperar, y lo razonable es
concluir que el sistema se rompió.
"""

from django.conf import settings
from django.shortcuts import render


def espera_legible(horas: float | int | None) -> str:
    """
    «15 minutos», «1 hora», «2 horas». Nunca «0.25».

    `AXES_COOLOFF_TIME` se declara en horas y admite fracciones, que es la
    unidad del ajuste y no la de quien lee la pantalla.
    """
    if not horas:
        return "unos minutos"
    if hasattr(horas, "total_seconds"):  # un timedelta, que axes también admite
        minutos = int(horas.total_seconds() // 60)
    else:
        minutos = int(round(float(horas) * 60))
    if minutos < 60:
        return f"{minutos} minuto{'s' if minutos != 1 else ''}"
    h = minutos // 60
    resto = minutos % 60
    texto = f"{h} hora{'s' if h != 1 else ''}"
    return f"{texto} y {resto} minutos" if resto else texto


def vista_bloqueado(request, credentials=None, *args, **kwargs):
    """
    Devuelve 429 —que es lo correcto— pero con una página que se entiende.

    El código de estado no se ablanda: un 200 aquí haría que un cliente
    automático no distinguiera un bloqueo de un acceso.
    """
    return render(
        request,
        "registration/bloqueado.html",
        {
            "intentos": getattr(settings, "AXES_FAILURE_LIMIT", 5),
            "espera": espera_legible(getattr(settings, "AXES_COOLOFF_TIME", None)),
        },
        status=429,
    )
