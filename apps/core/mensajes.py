"""Texto de error legible a partir de una excepción."""


def detalle_de_error(exc, por_defecto: str) -> str:
    """
    El texto de un `ValidationError`, o un mensaje claro si la excepción no lo
    trae.

    Existe porque los `except` de las pantallas capturan varias excepciones a la
    vez —`ValidationError`, `KeyError` de un campo que no llegó, el
    `DoesNotExist` de una clave foránea— y solo la primera tiene `.messages`.
    Escribir `"; ".join(exc.messages)` a secas convierte el manejador de errores
    en un error: `AttributeError` dentro del `except`, y una página 500 justo
    donde se iba a mostrar el aviso. Pasó en Laboratorio.
    """
    return "; ".join(exc.messages) if hasattr(exc, "messages") else por_defecto
