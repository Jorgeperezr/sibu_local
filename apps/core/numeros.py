"""
Leer un número escrito como se escribe aquí.

En Ecuador el separador decimal es la **coma**: 450,50 son cuatrocientos
cincuenta dólares con cincuenta centavos. El sistema tenía cuatro lecturas
distintas del mismo texto, todas silenciosas y todas alimentando la misma
decisión —el puntaje socioeconómico que orienta una beca—:

| Dónde                       | «450,50» se leía como |
|-----------------------------|-----------------------|
| Carga institucional         | 45050  (×100)         |
| Suma de ingresos del hogar  | se descartaba (0)     |
| Signos vitales              | se guardaba vacío     |
| Laboratorio                 | 450.50  (correcto)    |

Ninguna avisaba. Un hogar que declaraba sus ingresos con coma podía aparecer
con cien veces más o con cero, y el estrato —«extrema vulnerabilidad» o «sin
vulnerabilidad económica»— cambia con eso.

Este módulo es la única lectura. Las reglas, en orden:

1. Vacío es vacío: `None`, `""` o espacios devuelven `None`, no cero. Cero es
   una declaración; la ausencia de dato no lo es.
2. Se retiran los espacios, el `$` y el `USD`: vienen en los archivos que
   entrega la institución y no cambian el número.
3. **Si aparecen coma y punto**, el de más a la derecha es el decimal y el
   otro es de miles. Cubre las dos convenciones sin adivinar: `1.234,56` y
   `1,234.56` son los dos 1234.56.
4. **Si aparece uno solo**, es el separador decimal: `450,50` y `450.50` son
   450.50.
5. Lo que no sea un número lanza `ValidationError` con el valor recibido.
   Quien llama decide si eso interrumpe o se anota.

La regla 4 deja un caso genuinamente ambiguo: `1.234` puede ser mil doscientos
treinta y cuatro o uno coma doscientos treinta y cuatro, y las dos lecturas se
diferencian en mil veces. No se adivina: se lee como decimal —que es lo que
dice la regla— y `es_ambiguo()` lo señala para que quien carga un archivo lo
vea en la bitácora en vez de enterarse por el estrato de una familia.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

# Lo que se retira antes de leer: símbolo de moneda, código y espacios de
# cualquier clase —los archivos traen espacios finos y no separables—.
_RUIDO = re.compile(r"[\s  ]|USD|usd|\$")

# Un separador solo, seguido de exactamente tres dígitos y con dígitos delante:
# `1.234` o `1,234`. Las dos lecturas posibles se diferencian en mil veces.
_AMBIGUO = re.compile(r"^-?\d+[.,]\d{3}$")


def _limpiar(valor) -> str:
    return _RUIDO.sub("", str(valor))


def es_ambiguo(valor) -> bool:
    """
    ¿El texto admite dos lecturas que difieren en mil veces?

    `1.234` es el caso: mil doscientos treinta y cuatro, o uno coma doscientos
    treinta y cuatro. Se usa para avisar, no para rechazar.
    """
    if valor in (None, ""):
        return False
    return bool(_AMBIGUO.match(_limpiar(valor)))


def a_decimal(valor, *, campo: str = "") -> Decimal | None:
    """
    El número que dice el texto, o `None` si no dice nada.

    Lanza `ValidationError` si hay algo escrito que no es un número: un
    «450,5O» con la letra O es un error de digitación, no una descripción, y
    tragárselo en silencio es como se pierde un ingreso declarado.
    """
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int | float):
        return Decimal(str(valor))

    texto = _limpiar(valor)
    if not texto:
        return None

    tiene_coma, tiene_punto = "," in texto, "." in texto
    if tiene_coma and tiene_punto:
        # El de más a la derecha manda: es el decimal, el otro es de miles.
        decimal, miles = (",", ".") if texto.rfind(",") > texto.rfind(".") else (".", ",")
        texto = texto.replace(miles, "").replace(decimal, ".")
    elif tiene_coma:
        texto = texto.replace(",", ".")

    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        nombre = f" de «{campo}»" if campo else ""
        raise ValidationError(
            f"El valor{nombre} «{valor}» no es un número. Escríbalo con coma "
            "decimal (450,50) o con punto (450.50)."
        ) from exc


def a_decimal_o(valor, por_defecto=None, *, campo: str = "") -> Decimal | None:
    """
    Como `a_decimal`, pero devuelve `por_defecto` en vez de lanzar.

    Para los datos que ya están guardados y pueden traer texto descriptivo
    —«no aplica», «ninguno»— donde debería haber un monto. En lo que una
    persona acaba de escribir se usa `a_decimal`: ahí un texto raro es un error
    que hay que decir, no un dato que se pueda ignorar.
    """
    try:
        leido = a_decimal(valor, campo=campo)
    except ValidationError:
        return por_defecto
    return por_defecto if leido is None else leido


def a_entero(valor, por_defecto=None, *, campo: str = "") -> int | None:
    """
    El entero que dice el texto, o `por_defecto`.

    `int("tres")` lanzaba `ValueError` sin que nadie lo capturara y el cálculo
    del puntaje devolvía una página de error.
    """
    leido = a_decimal_o(valor, None, campo=campo)
    return por_defecto if leido is None else int(leido)
