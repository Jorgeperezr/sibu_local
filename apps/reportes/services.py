"""
Indicadores agregados para la gestión de la Unidad.

Regla de confidencialidad que gobierna el módulo: los tableros muestran
GESTIÓN, no contenido clínico. Psicología aparece solo como conteos agregados
—la Dirección necesita saber cuánta demanda atiende el servicio— y en los
desgloses finos se aplica supresión de celdas pequeñas: un cruce (carrera ×
periodo, por ejemplo) con menos de K_MINIMO casos en un servicio confidencial
no se muestra, porque un conteo de 1 identifica a la persona tan bien como su
nombre.
"""

from django.db.models import Count, Q
from django.utils import timezone

from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES

K_MINIMO = 5  # umbral de supresión para desgloses de servicios confidenciales
SUPRIMIDO = "<5"


def _suprimir(codigo_servicio: str, n: int):
    """En servicios confidenciales, un conteo pequeño se reporta como '<5'."""
    if codigo_servicio in SERVICIOS_CONFIDENCIALES and 0 < n < K_MINIMO:
        return SUPRIMIDO
    return n


def atenciones_por_servicio(desde=None, hasta=None) -> list[dict]:
    """Demanda por servicio. Psicología: solo el conteo, jamás el detalle."""
    from apps.expediente.models import Atencion

    qs = Atencion.objects.all()
    if desde:
        qs = qs.filter(fecha_hora__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_hora__date__lte=hasta)
    filas = (
        qs.values("servicio__codigo", "servicio__nombre")
        .annotate(total=Count("id"), pacientes=Count("expediente", distinct=True))
        .order_by("-total")
    )
    return [
        {
            "servicio": f["servicio__nombre"],
            # El total también se suprime bajo el umbral, y no por simetría:
            # los pacientes distintos nunca superan al total, así que un total
            # de 2 dice que los pacientes suprimidos son 1 o 2, y un total de 1
            # los revela exactamente. Publicar el total mientras se suprime el
            # otro dato dejaba reconstruirlo. Por encima del umbral no hay nada
            # que deducir y la demanda se ve completa.
            "total": _suprimir(f["servicio__codigo"], f["total"]),
            # "2 pacientes en psicología en la carrera X" señala a alguien.
            "pacientes": _suprimir(f["servicio__codigo"], f["pacientes"]),
        }
        for f in filas
    ]


def citas_indicadores(desde=None, hasta=None) -> dict:
    """Uso de la agenda: demanda, ausentismo y canal."""
    from apps.citas.models import Cita

    qs = Cita.objects.all()
    if desde:
        qs = qs.filter(fecha_hora__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_hora__date__lte=hasta)
    total = qs.count()
    por_estado = dict(qs.values_list("estado").annotate(n=Count("id")))
    atendidas = por_estado.get(Cita.Estado.ATENDIDA, 0)
    ausencias = por_estado.get(Cita.Estado.NO_ASISTIO, 0)
    finalizadas = atendidas + ausencias
    return {
        "total": total,
        "por_estado": por_estado,
        "por_canal": dict(qs.values_list("origen").annotate(n=Count("id"))),
        # El ausentismo se calcula sobre citas que llegaron a su hora
        # (atendida o no asistió), no sobre el total: contra reservas futuras
        # o canceladas a tiempo el indicador mentiría.
        "ausentismo_pct": round(ausencias * 100 / finalizadas, 1) if finalizadas else None,
    }


def derivaciones_indicadores() -> dict:
    """Flujo entre servicios. El destino confidencial aparece, su contenido no."""
    from apps.derivaciones.models import Derivacion

    filas = (
        Derivacion.objects.values("servicio_destino__codigo", "servicio_destino__nombre")
        .annotate(
            total=Count("id"),
            atendidas=Count("id", filter=Q(estado__in=["atendida", "retornada"])),
        )
        .order_by("-total")
    )
    return {
        "por_destino": [
            {
                "destino": f["servicio_destino__nombre"],
                # Mismo criterio que en atenciones_por_servicio: "1 derivación a
                # Psicología en el periodo" es un conteo pequeño sobre un
                # servicio confidencial, y cruzado con quién pasó por la Unidad
                # ese día señala igual que un nombre. El flujo entre servicios
                # se sigue viendo; lo que se vela es el tramo que identifica.
                "total": _suprimir(f["servicio_destino__codigo"], f["total"]),
                "atendidas": _suprimir(f["servicio_destino__codigo"], f["atendidas"]),
            }
            for f in filas
        ],
        "por_estado": dict(Derivacion.objects.values_list("estado").annotate(n=Count("id"))),
    }


def odontologia_cpod() -> dict:
    """
    CPO-D promedio: el indicador OMS que la Unidad reporta.

    El índice vive dentro del JSON `indices` (se congela al cerrar la
    atención), así que se promedia en Python: son pocas filas y el JSON no se
    agrega bien de forma portable entre SQLite y PostgreSQL.
    """
    from apps.odontologia.models import AtencionOdontologia

    valores = [
        fila["indices"]["cpod"]
        for fila in AtencionOdontologia.objects.exclude(indices={}).values("indices")
        if isinstance(fila["indices"], dict) and "cpod" in fila["indices"]
    ]
    return {
        "promedio": round(sum(valores) / len(valores), 2) if valores else 0,
        "atenciones_con_indice": len(valores),
    }


def psicopedagogia_impacto() -> dict:
    """Variación promedio del rendimiento en seguimientos con ambos promedios."""
    from apps.psicopedagogia.models import SeguimientoAcademico

    qs = SeguimientoAcademico.objects.filter(
        promedio_antes__isnull=False, promedio_despues__isnull=False
    )
    comparables = qs.count()
    if not comparables:
        return {"comparables": 0, "variacion_promedio": None}
    suma = sum(float(s.promedio_despues - s.promedio_antes) for s in qs)
    return {"comparables": comparables, "variacion_promedio": round(suma / comparables, 2)}


def laboratorio_indicadores() -> dict:
    from apps.laboratorio.models import OrdenLaboratorio

    return {
        "por_estado": dict(OrdenLaboratorio.objects.values_list("estado").annotate(n=Count("id"))),
    }


def becas_resumen() -> list[dict]:
    from apps.becas import services as becas_services
    from apps.core.models import PeriodoAcademico

    periodo = PeriodoAcademico.objects.filter(vigente=True).first()
    return becas_services.resumen_por_tipo(periodo) if periodo else []


def talleres_cobertura() -> dict:
    from apps.talleres import services as talleres_services

    return talleres_services.cobertura()


def tablero_general(desde=None, hasta=None) -> dict:
    """El tablero completo de la Dirección. Solo agregados; cero identidades."""
    return {
        "generado_en": timezone.now(),
        "atenciones": atenciones_por_servicio(desde, hasta),
        "citas": citas_indicadores(desde, hasta),
        "derivaciones": derivaciones_indicadores(),
        "odontologia": odontologia_cpod(),
        "psicopedagogia": psicopedagogia_impacto(),
        "laboratorio": laboratorio_indicadores(),
        "becas": becas_resumen(),
        "talleres": talleres_cobertura(),
    }


# ============================================================
# Informe estadístico de un servicio (RF nuevo: perfil de la
# población atendida, no gestión agregada de la Unidad)
# ============================================================
#
# A diferencia de `tablero_general` —que agrega TODOS los servicios para la
# Dirección y por eso aplica K_MÍNIMO—, este informe lo genera un profesional
# sobre SU PROPIO servicio: alguien que ya tiene acceso legítimo al contenido
# clínico completo de esos pacientes. No hay rendija que abrir ni celda que
# suprimir; es el mismo dato que ya ve atención por atención, solo que sumado.
#
# Nueve variables: estamento, sexo, género, identidad de género u orientación
# sexual —un solo ítem, no dos—, discapacidad, embarazo, lactancia, enfermedad
# catastrófica y necesidad educativa especial. El profesional ELIGE cuáles
# incluir: un informe de Medicina no necesita la necesidad educativa especial y
# uno de Psicopedagogía vive de ella, y obligar a las nueve hace que quien lee
# el informe se acostumbre a saltarse tablas. Solo sexo y discapacidad
# tenían dónde vivir en el modelo; embarazo, lactancia y enfermedad
# catastrófica no existían en ninguna parte del sistema —ni siquiera la carga
# académica masiva los guardaba en un campo consultable, se perdían en la
# fila cruda—. Se resuelven con `AlertaClinica`, que ya existe justo para
# banderas de este tipo (`Tipo.GESTACION`, `Tipo.LACTANCIA`,
# `Tipo.ENF_CATASTROFICA`) y con `Persona.identidad_orientacion_sexual`,
# nuevo (reemplaza a `Persona.etnia`, que no era una de las ocho variables
# pedidas y no tenía ningún otro uso en el sistema: ni el alta la recogía).
#
# Todas las columnas leen el estado VIGENTE de la persona/expediente al
# momento de generar el informe, no un dato histórico por atención: ni sexo,
# ni identidad/orientación sexual, ni una alerta llevan fecha de vigencia. Es
# la misma limitación que ya tiene el resto del sistema (el nombre de un
# paciente en la línea de tiempo es el actual, no el de cuando se abrió cada
# atención) — no es una inconsistencia nueva.
#
# Cada categoría lleva su porcentaje sobre el TOTAL DE ATENCIONES del rango
# (no sobre el total de pacientes): con 100 atenciones en el mes y 10 de una
# categoría, esa categoría es 10 %. Y el informe separa explícitamente
# atenciones de pacientes distintos, porque no son lo mismo: una persona
# atendida tres veces en el rango pesa tres atenciones, pero es una sola
# persona atendida.
#
# El estamento es `Persona.tipo_vinculo`, no un campo nuevo: ver el porqué en
# `Persona.TipoVinculo`.

SIN_DATO = "Sin dato"
SI = "Sí"
NO = "No"

# Los mismos tres tipos de alerta se consultan para tres columnas distintas.
_ALERTA_POR_COLUMNA = {
    "embarazo": "gestacion",
    "lactancia": "lactancia",
    "enfermedad_catastrofica": "enf_catastrofica",
    "necesidad_educativa_especial": "nee",
}

# Las variables del informe, en el orden en que se reportan. El profesional
# elige cuáles incluir; esta es la lista de lo que se puede elegir, y es la
# misma que usan la pantalla, el PDF, el Excel y los anexos: una segunda lista
# escrita a mano en la plantilla acabaría ofreciendo una casilla que el
# servicio no sabe calcular.
VARIABLES = {
    "estamento": "Estamento",
    "sexo": "Sexo",
    "genero": "Género",
    "identidad_orientacion_sexual": "Identidad u orientación sexual",
    "discapacidad": "Discapacidad",
    "embarazo": "Embarazo",
    "lactancia": "Lactancia",
    "enfermedad_catastrofica": "Enfermedad catastrófica",
    "necesidad_educativa_especial": "Necesidad educativa especial",
}

# Dos formas distintas de contar, y la diferencia importa al leer el informe:
#
# - de CATEGORÍA: cada atención cae en exactamente una etiqueta («Mujer»,
#   «Docente», «Sin dato»), así que la columna suma el total de atenciones.
# - de BANDERA: presencia o ausencia de una alerta activa. Se reporta cuántas
#   la tenían, no un desglose.
VARIABLES_DE_CATEGORIA = [
    "estamento",
    "sexo",
    "genero",
    "identidad_orientacion_sexual",
    "discapacidad",
]
VARIABLES_DE_BANDERA = list(_ALERTA_POR_COLUMNA)


def normalizar_variables(variables=None) -> list[str]:
    """
    Las variables pedidas, en el orden canónico y sin las que no existen.

    `None` significa «todas» —es lo que pide quien no eligió nada, y lo que
    hacía el informe antes de poder elegir—. Una lista vacía, en cambio, es una
    elección: el informe sale solo con los totales.
    """
    if variables is None:
        return list(VARIABLES)
    pedidas = set(variables)
    return [clave for clave in VARIABLES if clave in pedidas]


def _porcentaje(parte: int, total: int) -> float:
    """Porcentaje a un decimal; 0 si no hay atenciones (evita dividir por 0)."""
    return round(100 * parte / total, 1) if total else 0.0


def _conteo(valores, total: int) -> list[dict]:
    """
    [(etiqueta, valor), ...] → [{etiqueta, total, porcentaje}, ...], de mayor
    a menor. El porcentaje es sobre `total` (las atenciones del rango), no
    sobre la suma de esta columna —son el mismo número solo porque cada
    atención aporta exactamente una etiqueta por columna—.
    """
    from collections import Counter

    conteo = Counter(valores)
    return [
        {"etiqueta": etiqueta, "total": n, "porcentaje": _porcentaje(n, total)}
        for etiqueta, n in sorted(conteo.items(), key=lambda par: -par[1])
    ]


# Campos que hay que traer de la base para clasificar una atención. Se declaran
# aquí y no en cada consulta para que el informe y sus anexos lean exactamente
# lo mismo: un anexo que se llamara «evidencia» y consultara por su cuenta
# podría no sumar la cifra que dice evidenciar.
CAMPOS_DE_CLASIFICACION = (
    "id",
    "fecha_hora",
    "expediente_id",
    "expediente__numero_expediente",
    "expediente__persona_id",
    "expediente__persona__tipo_vinculo",
    "expediente__persona__sexo",
    "expediente__persona__genero",
    "expediente__persona__identidad_orientacion_sexual",
    "expediente__discapacidad_tipo",
)


def atenciones_del_informe(servicio, desde=None, hasta=None):
    """La consulta base del informe y de sus anexos: una sola definición."""
    from apps.expediente.models import Atencion

    qs = Atencion.objects.filter(servicio=servicio)
    if desde:
        qs = qs.filter(fecha_hora__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_hora__date__lte=hasta)
    return qs


def etiquetar(servicio, filas: list[dict]) -> list[dict]:
    """
    La etiqueta que le toca a cada atención en CADA variable.

    Es el corazón compartido: el informe cuenta estas etiquetas y el anexo de
    evidencias agrupa por ellas. Si esto fuera dos implementaciones, la
    evidencia podría contradecir a la cifra que respalda, que es justo lo que
    un anexo existe para impedir.
    """
    from apps.core import vocabulario
    from apps.expediente.models import AlertaClinica, Persona

    expediente_ids = {f["expediente_id"] for f in filas}
    alertas_activas = set(
        AlertaClinica.objects.filter(
            expediente_id__in=expediente_ids,
            tipo__in=_ALERTA_POR_COLUMNA.values(),
            activa=True,
        ).values_list("expediente_id", "tipo")
    )

    # Lo que ESTE servicio comprobó en consulta, que puede contradecir a la
    # matrícula: la ficha decía que no había embarazo y aquí se registró uno.
    # Sin esto el informe contaría la foto del día de la matrícula y no lo que
    # el servicio sabe. Los ajustes de otros servicios no cuentan: cada uno
    # reporta lo que él comprobó.
    from apps.expediente.selectors import expedientes_con_ajuste

    ajustados_si = {
        tipo: expedientes_con_ajuste(servicio, tipo, "Sí") for tipo in _ALERTA_POR_COLUMNA.values()
    }
    ajustados_no = {
        tipo: expedientes_con_ajuste(servicio, tipo, "No") for tipo in _ALERTA_POR_COLUMNA.values()
    }

    def _tiene(expediente_id: int, codigo_tipo: str) -> bool:
        """El ajuste del servicio manda; si no lo hay, la alerta institucional."""
        if expediente_id in ajustados_si[codigo_tipo]:
            return True
        if expediente_id in ajustados_no[codigo_tipo]:
            # Un «No» del servicio también manda: si aquí se comprobó que la
            # gestación terminó, contarla seguiría inflando el informe.
            return False
        return (expediente_id, codigo_tipo) in alertas_activas

    estamentos = dict(Persona.TipoVinculo.choices)
    etiquetadas = []
    for f in filas:
        # `vocabulario.normalizar` agrupa el mismo valor escrito de varias
        # maneras. Cada estamento entrega su propia base y cada archivo escribe
        # a la suya: el informe contaba «F 6, M 6, Mujer 3, Hombre 2» donde hay
        # dos grupos, y así se entregaba. Agrupa al contar, no al guardar: lo
        # declarado se conserva tal cual en el expediente.
        etiquetas = {
            "estamento": estamentos.get(f["expediente__persona__tipo_vinculo"], SIN_DATO),
            "sexo": vocabulario.normalizar("sexo", f["expediente__persona__sexo"]) or SIN_DATO,
            "genero": (
                vocabulario.normalizar("genero", f["expediente__persona__genero"]) or SIN_DATO
            ),
            "identidad_orientacion_sexual": (
                vocabulario.normalizar(
                    "identidad_orientacion_sexual",
                    f["expediente__persona__identidad_orientacion_sexual"],
                )
                or SIN_DATO
            ),
            "discapacidad": (
                "Con discapacidad" if f["expediente__discapacidad_tipo"] else "Sin discapacidad"
            ),
        }
        for columna, codigo_tipo in _ALERTA_POR_COLUMNA.items():
            etiquetas[columna] = SI if _tiene(f["expediente_id"], codigo_tipo) else NO
        etiquetadas.append({**f, "etiquetas": etiquetas})
    return etiquetadas


def informe_estadistico(servicio, desde=None, hasta=None, variables=None) -> dict:
    """
    Perfil estadístico de las atenciones de un servicio en un rango de fechas.

    Cuenta ATENCIONES, no pacientes distintos, para las columnas por
    categoría: una persona atendida tres veces en el rango pesa tres veces,
    igual que en un parte de consulta diario (RDACAA). `total_pacientes`
    aparte da la otra cifra —cuántas personas distintas hay detrás de esas
    atenciones— porque las dos preguntas ("cuánta demanda" y "a cuánta gente")
    tienen respuestas distintas y ninguna sustituye a la otra.

    `variables` es lo que el profesional decidió incluir. Los dos totales van
    siempre: un informe sin ellos no se puede leer, porque todos los
    porcentajes son sobre las atenciones.
    """
    from django.utils import timezone as tz

    incluidas = normalizar_variables(variables)
    filas = list(atenciones_del_informe(servicio, desde, hasta).values(*CAMPOS_DE_CLASIFICACION))
    total_atenciones = len(filas)
    total_pacientes = len({f["expediente_id"] for f in filas})
    etiquetadas = etiquetar(servicio, filas) if incluidas else []

    datos = {
        "servicio": servicio,
        "desde": desde,
        "hasta": hasta,
        "generado_en": tz.now(),
        "total_atenciones": total_atenciones,
        "total_pacientes": total_pacientes,
        "variables": incluidas,
        # Lo que la plantilla recorre. Antes cada tabla estaba escrita a mano en
        # el HTML y en el PDF; con variables elegibles eso serían dos listas más
        # que mantener sincronizadas con esta.
        "secciones": [],
    }
    for clave in incluidas:
        etiqueta = VARIABLES[clave]
        valores = (f["etiquetas"][clave] for f in etiquetadas)
        if clave in VARIABLES_DE_CATEGORIA:
            conteo = _conteo(valores, total_atenciones)
            datos[clave] = conteo
            datos["secciones"].append(
                {"clave": clave, "etiqueta": etiqueta, "tipo": "categoria", "filas": conteo}
            )
        else:
            # Presencia/ausencia: se reporta cuántas atenciones la tenían
            # activa, no el desglose sí/no, que sería la misma cifra dos veces.
            n = sum(1 for v in valores if v == SI)
            resumen = {"total": n, "porcentaje": _porcentaje(n, total_atenciones)}
            datos[clave] = resumen
            datos["secciones"].append(
                {"clave": clave, "etiqueta": etiqueta, "tipo": "bandera", **resumen}
            )
    # Las plantillas las necesitan separadas: las de categoría son una tabla
    # cada una y las banderas van todas en la misma. Se parten aquí porque una
    # plantilla no puede filtrar una lista sin un bucle vacío que la ensucie.
    datos["categorias"] = [s for s in datos["secciones"] if s["tipo"] == "categoria"]
    datos["banderas"] = [s for s in datos["secciones"] if s["tipo"] == "bandera"]
    return datos
