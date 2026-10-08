"""
Agrupar el mismo valor escrito de varias maneras.

Cada estamento entrega su propia base y cada archivo escribe a su manera: el de
estudiantes trae «F» y «M», el de docentes «Mujer» y «Hombre», y la captura
manual lo que teclee quien atiende. Son dos grupos, pero el informe los contaba
como cuatro filas —«F 6, M 6, Mujer 3, Hombre 2»— y así se entrega a la
Dirección.

Dos niveles, y la diferencia importa:

1. **Tipográfico, para toda variable declarada**: se recortan espacios y se
   unifica la capitalización. «femenino» y «Femenino» son el mismo valor
   escrito distinto; juntarlos no impone ninguna categoría.

2. **Sinónimos, solo donde el vocabulario es oficial y cerrado.** El sexo lo
   es (RDACAA: mujer, hombre, intersexual), así que «F», «f» y «Femenino» se
   cuentan como «Mujer».

Lo que NO se toca es el género y la identidad u orientación sexual: son campos
libres a propósito —el modelo lo dice y `AjusteDeServicio` los declara no
ajustables—, y meterles una tabla de sinónimos sería decidir por la persona
cómo se nombra. Ahí solo se aplica el nivel 1.

Esto agrupa al CONTAR, no al guardar. Lo declarado se conserva tal cual en el
expediente: el informe dice cuántas hay, no reescribe lo que dijo nadie.
"""

from __future__ import annotations

# Vocabularios oficiales y cerrados. clave = variable, valor = {escritura: forma}
# Las escrituras se comparan en minúsculas y sin espacios sobrantes.
SINONIMOS = {
    "sexo": {
        "f": "Mujer",
        "fem": "Mujer",
        "femenino": "Mujer",
        "mujer": "Mujer",
        "m": "Hombre",
        "masc": "Hombre",
        "masculino": "Hombre",
        "hombre": "Hombre",
        "i": "Intersexual",
        "intersexual": "Intersexual",
    },
}


def normalizar(variable: str, valor: str) -> str:
    """
    La forma con la que se cuenta ese valor.

    Sin sinónimos declarados devuelve el valor con los espacios recortados y la
    primera letra en mayúscula, que es lo que junta «femenino» con «Femenino»
    sin decidir nada sobre el contenido.
    """
    texto = (valor or "").strip()
    if not texto:
        return texto
    tabla = SINONIMOS.get(variable)
    if tabla:
        forma = tabla.get(texto.casefold())
        if forma:
            return forma
    # `capitalize()` no vale: destruiría «VIH/SIDA» o un nombre compuesto.
    return texto[0].upper() + texto[1:]
