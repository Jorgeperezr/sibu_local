"""
Plurales en español para las plantillas.

`pluralize` de Django pega una terminación al final de la palabra tal cual
está escrita, y en español eso falla cada vez que el singular lleva tilde en la
última sílaba: «atención» + «es» da «atencions» si se pega la s, y escribir
`atencion{{ n|pluralize:"es" }}` para esquivarlo imprime «1 atencion», sin
tilde. Ya estaba resuelto a mano en dos sitios —el subtítulo del Excel y la
pantalla de exportación, las dos con su comentario explicándolo— y se volvió a
colar en los anexos del informe: se veía «1 atencion» en pantalla y en el PDF.

Por eso el filtro pide las DOS formas, que es la única manera de no equivocarse:

    {{ n }} {{ n|plural:"atención,atenciones" }}
"""

from decimal import Decimal, InvalidOperation

from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter
def plural(cantidad, formas: str) -> str:
    """
    La forma que toca según la cantidad. `formas` es "singular,plural".

    Uno es singular y todo lo demás plural, cero incluido: en español se dice
    «0 atenciones».
    """
    singular, _, plural_ = formas.partition(",")
    try:
        uno = int(cantidad) == 1
    except (TypeError, ValueError):
        uno = False
    return singular if uno else (plural_ or singular)


@register.filter
def numero(valor) -> str:
    """
    Un decimal sin los ceros de relleno con que lo guarda la base.

    Los rangos de referencia del laboratorio son `DecimalField(decimal_places=3)`,
    así que la hemoglobina se imprimía «12,000 – 16,000». En español la coma es
    decimal y eso es doce coma cero, pero quien lo lee de reojo ve doce mil, y
    es la pantalla donde un valor mal leído tiene consecuencias clínicas. Aquí
    sale «12 – 16», y un 0,300 sale «0,3».

    Cero devuelve «0», no cadena vacía: cero es un valor, y confundirlo con la
    ausencia de dato es justo el defecto que se está arreglando al lado.
    """
    if valor is None or valor == "":
        return ""
    try:
        decimal = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return str(valor)

    recortado = decimal.normalize()
    if recortado == recortado.to_integral_value():
        # `normalize()` deja 12.000 en notación científica (1.2E+1).
        recortado = recortado.quantize(Decimal(1))
    decimales = max(-recortado.as_tuple().exponent, 0)
    return number_format(recortado, decimal_pos=decimales, use_l10n=True)
