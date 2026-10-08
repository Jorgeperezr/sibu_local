"""
Leer los parámetros de una URL sin que un disparate acabe en un 500.

Lo que llega por la barra de direcciones puede ser cualquier cosa. Django lo
recuerda al filtrar: `filter(expediente_id="abc")` lanza `ValueError: Field
'id' expected a number`, y esa excepción sale sin capturar. Una consulta mal
escrita es un 400, nunca una avería del servidor.

La otra mitad importa más: **un filtro que no se puede leer no puede
ignorarse**. Si `?expediente=abc` se tradujera a «sin filtro», la respuesta
traería las fichas de TODAS las personas a quien pidió las de una. Un 400 dice
que no se entendió; devolver de más dice otra cosa.
"""

from __future__ import annotations

from rest_framework.exceptions import ValidationError as ErrorDePeticion

from . import numeros


def id_de_consulta(valor, campo: str = "id"):
    """
    El identificador que trae el parámetro, `None` si no vino, o 400.

    `None` significa «no lo pidió» y quien llama decide qué hacer con eso.
    Lo que no puede pasar por `None` es un valor ilegible: eso es una petición
    equivocada y se responde como tal.
    """
    if valor in (None, ""):
        return None
    leido = numeros.a_entero(valor, None)
    if leido is None or leido < 0:
        raise ErrorDePeticion({campo: f"«{valor}» no es un identificador válido."})
    return leido
