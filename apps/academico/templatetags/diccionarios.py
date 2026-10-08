"""
Acceso a un diccionario por una clave que es variable.

Las plantillas de Django resuelven `{{ d.clave }}` buscando la clave literal
«clave», no el valor de la variable. Con los filtros del padrón hace falta lo
segundo: la clave viene del bucle.
"""

from django import template

registro = template.Library()
register = registro  # Django busca el nombre en inglés.


@registro.filter
def dictkey(diccionario, clave):
    """`{{ opciones|dictkey:clave }}`. Devuelve vacío si no está, nunca error."""
    try:
        return diccionario.get(clave, "")
    except AttributeError:
        return ""
