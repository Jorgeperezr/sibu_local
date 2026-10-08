"""
Vocabulario de la ficha socioeconómica: qué casillas tiene y cómo se llaman.

Las claves son las mismas que trae la ficha de matrícula (`academico.mapping`),
no unas propias. Tenerlas distintas era el motivo de que un dato cargado desde
matrícula no apareciera nunca en la pantalla de Trabajo Social: la carga escribía
`ingreso_padre` y el formulario preguntaba por `sueldo_padre`.

Las etiquetas sí viven aquí: `mapping` congela el diccionario oficial del archivo
y no debe cargar con cómo se rotula cada cosa en pantalla.
"""

from __future__ import annotations

# Totales declarados por el estudiante en matrícula. NO son una línea más del
# desglose: son la suma que él mismo reportó. Sumarlos junto a sus componentes
# duplicaba el ingreso del hogar y, con él, el puntaje que orienta una beca.
TOTALES_DECLARADOS = {"ingreso_mensual", "gastos_mensual_familia"}

INGRESOS = [
    ("ingreso_estudiante", "Del estudiante"),
    ("ingreso_padre", "Del padre"),
    ("ingreso_madre", "De la madre"),
    ("ingreso_conyuge", "Del cónyuge"),
    ("ingreso_otro_familiar", "De otro familiar"),
    ("ingreso_arriendo", "Por arriendo"),
    ("ingreso_pension_judicial", "Pensión judicial"),
    ("ingreso_fondo_estado", "Fondo del Estado"),
    ("ingreso_beca_senescyt", "Beca SENESCYT"),
    ("ingreso_beca_unl", "Beca UNL"),
    ("ingreso_otro", "Otro ingreso"),
]

EGRESOS = [
    ("gastos_vivienda", "Vivienda"),
    ("gastos_alimentacion", "Alimentación"),
    ("gastos_estudios", "Estudios"),
    ("gastos_transporte", "Transporte"),
    ("gastos_salud", "Salud"),
    ("gastos_vestuario", "Vestuario"),
    ("gastos_servicio_basico", "Servicios básicos"),
    ("gastos_tarjeta_credito", "Tarjeta de crédito"),
    ("gastos_otro", "Otro gasto"),
    ("credito_educativo_valor", "Cuota de crédito educativo"),
]

# Grupos que la carga de matrícula pre-puebla y que la pantalla muestra en solo
# lectura: son declaraciones del estudiante, no algo que Trabajo Social corrija
# desde aquí. Verlas es lo que evita volver a preguntar lo ya preguntado.
GRUPOS_INFORMATIVOS = [
    ("vivienda_estudiante", "Vivienda del estudiante"),
    ("vivienda_familiar", "Vivienda familiar"),
    ("situacion_laboral", "Situación laboral"),
    ("salud_familiar", "Salud familiar"),
    ("convivencia", "Convivencia y entorno académico"),
]


def etiquetas() -> dict[str, str]:
    """Clave canónica -> rótulo, para mostrar los grupos informativos."""
    legibles = {}
    for clave, rotulo in INGRESOS + EGRESOS:
        legibles[clave] = rotulo
    return legibles


def rotular(clave: str) -> str:
    """
    Rótulo legible de una clave cualquiera de la ficha.

    Las claves de los grupos informativos son decenas y cambian con el archivo
    de cada período; en vez de mantener un diccionario que se quedaría corto, se
    derivan: `viv_est_servicio_agua_potable` -> «Viv est servicio agua potable».
    """
    return etiquetas().get(clave) or clave.replace("_", " ").capitalize()
