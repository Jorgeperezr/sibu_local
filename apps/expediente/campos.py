"""
Vocabulario del alta de personas: qué casillas tiene y cómo se rotulan.

Las claves de los grupos son las MISMAS que trae la ficha de matrícula
(`academico.mapping.PERSONA_JSONB`), no unas propias. Tenerlas distintas ya
costó caro en Trabajo Social: la carga escribía `ingreso_padre`, el formulario
preguntaba por `sueldo_padre`, y un dato cargado no aparecía nunca en pantalla.
Aquí se evita de antemano.

Los rótulos sí viven aquí: `mapping` congela el diccionario oficial del archivo
institucional y no debe cargar con cómo se escribe cada cosa en la interfaz.
"""

from __future__ import annotations

from apps.academico import mapping

# Campos sueltos de `Persona`. Ninguno es obligatorio salvo los tres que el
# servicio exige (cédula, nombres, apellidos).
CAMPOS_PERSONA = (
    "cedula",
    "tipo_documento",
    "nombres",
    "apellidos",
    "fecha_nacimiento",
    "sexo",
    "genero",
    "identidad_orientacion_sexual",
    "tipo_vinculo",
    "correo_institucional",
    "correo_personal",
    "telefono",
    "celular",
)

# Campos que viven en el `Expediente`, no en la `Persona`.
CAMPOS_EXPEDIENTE = ("grupo_sanguineo", "discapacidad_tipo", "discapacidad_porcentaje")

# Grupos que se guardan como JSON. (prefijo del formulario, atributo, título).
GRUPOS_JSON = (
    ("procedencia", "procedencia", "Procedencia"),
    ("residencia", "residencia_actual", "Residencia actual"),
    ("referencia", "contacto_referencia", "Contacto de referencia"),
)

# Rótulos de las claves de esos grupos. Lo que no esté aquí se deriva de la
# propia clave, así que añadir una columna al mapeo no deja un hueco en blanco.
ROTULOS = {
    "pais_procedencia": "País",
    "provincia_procedencia": "Provincia",
    "canton_procedencia": "Cantón",
    "parroquia_procedencia": "Parroquia",
    "barrio_procedencia": "Barrio",
    "direccion_procedencia": "Dirección",
    "pais_actual": "País",
    "provincia_actual": "Provincia",
    "canton_actual": "Cantón",
    "parroquia_actual": "Parroquia",
    "barrio_actual": "Barrio",
    "calle_principal_actual": "Calle principal",
    "calle_secundaria_actual": "Calle secundaria",
    "referencia_actual": "Referencia del domicilio",
    "numero_casa_actual": "Número de casa",
    "zona_actual": "Zona",
    "representante_nombres": "Nombres del contacto",
    "representante_direccion": "Dirección del contacto",
    "representante_referencia": "Referencia",
    "representante_telefono": "Teléfono del contacto",
    "responsable_persona": "Parentesco o responsable",
}


def rotular(clave: str) -> str:
    """Rótulo legible de una clave; derivado de ella misma si no está listada."""
    return ROTULOS.get(clave) or clave.replace("_", " ").capitalize()


def grupos_para_formulario(valores: dict | None = None) -> list[dict]:
    """
    Los grupos JSON listos para dibujar, con lo ya escrito de vuelta en su sitio.

    Devolver los valores importa: cuando el alta se rechaza —una cédula que no
    pasa el módulo 10— el formulario se vuelve a pintar, y sin esto la persona
    perdería todo lo que hubiera tecleado en estos grupos.
    """
    valores = valores or {}
    grupos = []
    for prefijo, atributo, titulo in GRUPOS_JSON:
        claves = mapping.PERSONA_JSONB[atributo]
        grupos.append(
            {
                "prefijo": prefijo,
                "titulo": titulo,
                "casillas": [
                    {
                        "nombre": f"{prefijo}-{clave}",
                        "etiqueta": rotular(clave),
                        "valor": valores.get(f"{prefijo}-{clave}", ""),
                    }
                    for clave in claves
                ],
            }
        )
    return grupos
