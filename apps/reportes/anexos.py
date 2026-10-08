"""
Anexos del informe estadístico: la nómina y la evidencia de lo reportado.

El informe da cifras; el anexo dice de dónde salen. Dos anexos, y la
diferencia entre ellos no es cosmética:

- **La nómina** es la lista de las personas atendidas en el periodo, una fila
  por persona, con las atenciones que suma cada una. Responde «¿a quiénes?».
- **La evidencia** es esa misma lista partida por el valor de cada variable
  incluida en el informe: quiénes componen el «14 mujeres», quiénes el «3 con
  discapacidad». Responde «¿de dónde sale esta cifra?».

Tres reglas gobiernan el módulo:

**1. Un anexo no puede contradecir al informe.** Las dos cosas se construyen
sobre `services.etiquetar`, no sobre dos consultas parecidas. Por eso la suma
de la columna «Atenciones» de un grupo de la evidencia es exactamente la cifra
que el informe reporta para ese grupo, y hay una prueba que lo comprueba.

**2. Los servicios confidenciales no llevan anexo.** Un anexo nombra a
pacientes en un archivo que sale de la Unidad. La cifra agregada de Psicología
sí se informa —el informe estadístico lo genera el propio servicio—, pero la
lista de nombres cae bajo la misma regla que impide exportar su historial, y se
comprueba con la misma función (`exportacion.verificar_exportable`) para que no
haya dos criterios que puedan separarse.

**3. La identidad va protegida salvo que se decida lo contrario.** Cédula,
teléfono, correo institucional y número de expediente no se imprimen a menos
que quien genera el informe los pida expresamente. El número de expediente está
en esa lista y no por simetría: se compone como `EXP-<cédula>`, así que
publicarlo mientras se oculta la cédula sería publicar la cédula. En su lugar
cada fila lleva un código correlativo del propio anexo (A-001, A-002…), que
sirve para citar una fila sin identificar a nadie fuera de él.

El NOMBRE no está entre lo que se retira, y es una decisión, no un olvido: una
nómina sin nombres deja de ser una nómina, y lo que se pidió proteger fue la
cédula, el teléfono y el correo institucional. Quien necesite un anexo
completamente anónimo desmarca también la columna «Apellidos y nombres»: el
código correlativo sostiene la fila igual.
"""

from __future__ import annotations

from django.utils import timezone

from . import services
from .exportacion import verificar_exportable

# Columnas que puede llevar un anexo. `identificativa` marca las que
# identifican a la persona ante quien recibe el documento: son las que la
# protección de identidad retira.
COLUMNAS = {
    "codigo": {"etiqueta": "Código", "identificativa": False},
    "nombre": {"etiqueta": "Apellidos y nombres", "identificativa": False},
    "cedula": {"etiqueta": "Cédula", "identificativa": True},
    "telefono": {"etiqueta": "Teléfono", "identificativa": True},
    "correo_institucional": {"etiqueta": "Correo institucional", "identificativa": True},
    "expediente": {"etiqueta": "N.º de expediente", "identificativa": True},
    "estamento": {"etiqueta": "Estamento", "identificativa": False},
    "facultad": {"etiqueta": "Facultad", "identificativa": False},
    "carrera": {"etiqueta": "Carrera", "identificativa": False},
    "sexo": {"etiqueta": "Sexo", "identificativa": False},
    "genero": {"etiqueta": "Género", "identificativa": False},
    "identidad_orientacion_sexual": {
        "etiqueta": "Identidad u orientación sexual",
        "identificativa": False,
    },
    "discapacidad": {"etiqueta": "Discapacidad", "identificativa": False},
    "atenciones": {"etiqueta": "Atenciones", "identificativa": False},
    "ultima_atencion": {"etiqueta": "Última atención", "identificativa": False},
}

IDENTIFICATIVAS = [c for c, d in COLUMNAS.items() if d["identificativa"]]

# Con qué sale el anexo si no se elige nada: quién es, de dónde y cuánto pesa.
# Ninguna identificativa entra por defecto.
COLUMNAS_POR_DEFECTO = ["codigo", "nombre", "estamento", "facultad", "carrera", "atenciones"]


def normalizar_columnas(columnas=None, proteger: bool = True) -> tuple[list[str], list[str]]:
    """
    (columnas que se imprimen, columnas retiradas por la protección).

    Se devuelven las retiradas y no solo las que quedan porque hay que
    DECIRLO al pie del anexo: una lista a la que se le quitaron columnas sin
    avisar se lee como la lista completa.

    El código correlativo va siempre el primero: es lo que permite citar una
    fila cuando el nombre no está.
    """
    pedidas = COLUMNAS_POR_DEFECTO if columnas is None else [c for c in columnas if c in COLUMNAS]
    elegidas = [c for c in COLUMNAS if c in set(pedidas)]
    if proteger:
        retiradas = [c for c in elegidas if COLUMNAS[c]["identificativa"]]
        elegidas = [c for c in elegidas if c not in retiradas]
    else:
        retiradas = []
    if "codigo" not in elegidas:
        elegidas.insert(0, "codigo")

    # Si no quedó ninguna columna con contenido, el anexo sería una lista de
    # códigos correlativos: A-001, A-002, A-003. No informa de nada y no se
    # distingue de un anexo bien hecho sobre datos que faltan, así que se cae a
    # las columnas por omisión en vez de imprimir eso. Pasa al desmarcarlas
    # todas —y el enlace del PDF y del Excel arrastra esa elección—, así que no
    # es un caso rebuscado; se vio en pantalla, no en una prueba.
    if elegidas == ["codigo"]:
        elegidas = [
            c for c in COLUMNAS_POR_DEFECTO if not (proteger and COLUMNAS[c]["identificativa"])
        ]
    return elegidas, retiradas


def _academicos(persona_ids: set[int]) -> dict:
    """El dato académico más reciente de cada persona, en UNA consulta."""
    from apps.academico.models import DatoAcademico

    if not persona_ids:
        return {}
    academicos = {}
    for dato in DatoAcademico.objects.filter(persona_id__in=persona_ids).order_by(
        "persona_id", "-periodo__fecha_inicio"
    ):
        academicos.setdefault(dato.persona_id, dato)
    return academicos


def _personas(servicio, desde, hasta) -> list[dict]:
    """
    Una fila por PERSONA atendida, con sus etiquetas y cuántas atenciones suma.

    Por persona y no por atención: una nómina que repitiera a quien vino tres
    veces se leería como tres personas. La columna «Atenciones» conserva el otro
    dato, que es el que suma la cifra del informe.
    """
    filas = list(
        services.atenciones_del_informe(servicio, desde, hasta).values(
            *services.CAMPOS_DE_CLASIFICACION
        )
    )
    etiquetadas = services.etiquetar(servicio, filas)

    por_expediente: dict[int, dict] = {}
    for fila in etiquetadas:
        registro = por_expediente.get(fila["expediente_id"])
        if registro is None:
            por_expediente[fila["expediente_id"]] = {
                "expediente_id": fila["expediente_id"],
                "persona_id": fila["expediente__persona_id"],
                "expediente": fila["expediente__numero_expediente"],
                "etiquetas": fila["etiquetas"],
                "atenciones": 1,
                "ultima_atencion": fila["fecha_hora"],
            }
            continue
        registro["atenciones"] += 1
        if fila["fecha_hora"] > registro["ultima_atencion"]:
            registro["ultima_atencion"] = fila["fecha_hora"]

    from apps.expediente.models import Persona

    personas = {
        p.pk: p
        for p in Persona.objects.filter(pk__in={r["persona_id"] for r in por_expediente.values()})
    }
    academicos = _academicos(set(personas))

    registros = []
    for registro in por_expediente.values():
        persona = personas.get(registro["persona_id"])
        academico = academicos.get(registro["persona_id"])
        registros.append(
            {
                **registro,
                "nombre": persona.nombre_completo if persona else "",
                "cedula": persona.cedula if persona else "",
                "telefono": (persona.celular or persona.telefono) if persona else "",
                "correo_institucional": persona.correo_institucional if persona else "",
                "facultad": academico.facultad if academico else "",
                "carrera": academico.carrera if academico else "",
            }
        )
    # Alfabético por nombre, incluso cuando el nombre no se imprime: así el
    # código correlativo es estable entre dos generaciones del mismo anexo.
    registros.sort(key=lambda r: r["nombre"])
    for numero, registro in enumerate(registros, start=1):
        registro["codigo"] = f"A-{numero:03d}"
    return registros


def _celda(registro: dict, columna: str):
    if columna in services.VARIABLES:
        return registro["etiquetas"].get(columna, "")
    if columna == "ultima_atencion":
        fecha = registro["ultima_atencion"]
        return timezone.localtime(fecha).strftime("%d/%m/%Y") if fecha else ""
    return registro.get(columna, "")


def nomina(servicio, desde=None, hasta=None, columnas=None, proteger: bool = True) -> dict:
    """
    La lista de las personas atendidas en el periodo, con las columnas pedidas.

    Lanza `ValidationError` si el servicio es confidencial: el informe agregado
    sí sale, la lista de nombres no.
    """
    verificar_exportable(servicio.codigo)
    elegidas, retiradas = normalizar_columnas(columnas, proteger)
    registros = _personas(servicio, desde, hasta)
    return {
        "columnas": elegidas,
        "encabezados": [COLUMNAS[c]["etiqueta"] for c in elegidas],
        "filas": [[_celda(r, c) for c in elegidas] for r in registros],
        "total": len(registros),
        "protegida": bool(proteger),
        "retiradas": [COLUMNAS[c]["etiqueta"] for c in retiradas],
    }


def evidencias(
    servicio, desde=None, hasta=None, variables=None, columnas=None, proteger: bool = True
) -> list[dict]:
    """
    De dónde sale cada cifra: las personas que componen cada valor reportado.

    Un grupo por (variable, valor). La suma de la columna «Atenciones» de un
    grupo es la cifra que el informe da para ese valor —de eso vive el anexo—,
    así que la columna se añade aunque no se haya pedido: sin ella el anexo
    listaría personas junto a un número que no cuenta personas, y quien lo lea
    concluiría que el informe está mal.
    """
    verificar_exportable(servicio.codigo)
    incluidas = services.normalizar_variables(variables)
    elegidas, retiradas = normalizar_columnas(columnas, proteger)
    if "atenciones" not in elegidas:
        elegidas = [*elegidas, "atenciones"]
    registros = _personas(servicio, desde, hasta)

    grupos = []
    for clave in incluidas:
        valores: dict[str, list[dict]] = {}
        for registro in registros:
            valores.setdefault(registro["etiquetas"][clave], []).append(registro)
        for valor, delgrupo in sorted(
            valores.items(), key=lambda par: -sum(r["atenciones"] for r in par[1])
        ):
            # Una bandera en «No» no es un valor reportado: el informe dice
            # cuántas atenciones LA TENÍAN, así que listar a quien no la tiene
            # sería un anexo de algo que no aparece en ninguna cifra.
            if clave in services.VARIABLES_DE_BANDERA and valor != services.SI:
                continue
            grupos.append(
                {
                    "variable": clave,
                    "etiqueta_variable": services.VARIABLES[clave],
                    "valor": valor,
                    "personas": len(delgrupo),
                    "atenciones": sum(r["atenciones"] for r in delgrupo),
                    "columnas": elegidas,
                    "encabezados": [COLUMNAS[c]["etiqueta"] for c in elegidas],
                    "filas": [[_celda(r, c) for c in elegidas] for r in delgrupo],
                    "protegida": bool(proteger),
                    "retiradas": [COLUMNAS[c]["etiqueta"] for c in retiradas],
                }
            )
    return grupos
