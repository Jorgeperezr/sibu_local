"""
Servicios del expediente único (informe 4.2, 5.2 M04).

Punto central para: vincular/crear el expediente de una persona por cédula,
construir el snapshot institucional que se congela en cada atención y consolidar
la línea de tiempo respetando el RBAC.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academico.providers import get_provider
from apps.academico.validators import normalizar_cedula

from .models import AlertaClinica, Expediente, Persona


def obtener_o_crear_expediente(persona: Persona, usuario=None) -> Expediente:
    """Devuelve el expediente de la persona; lo crea si no existe."""
    expediente, creado = Expediente.objects.get_or_create(
        persona=persona,
        defaults={"numero_expediente": f"EXP-{persona.cedula}", "creado_por": usuario},
    )
    return expediente


def _porcentaje_de_discapacidad(valor):
    """
    El porcentaje, o None si no se escribió. Fuera de 0-100, se rechaza aquí.

    `Expediente` lleva una CheckConstraint que lo limita a 100. Sin esta
    comprobación, un 150 tecleado por error saldría como IntegrityError —una
    pantalla de error 500— en vez de como un aviso que se puede corregir.
    """
    valor = (str(valor) if valor is not None else "").strip()
    if not valor:
        return None
    if not valor.isdigit():
        raise ValidationError("El porcentaje de discapacidad debe ser un número entero.")
    numero = int(valor)
    if numero > 100:
        raise ValidationError("El porcentaje de discapacidad no puede pasar de 100.")
    return numero


def _grupo_json(datos: dict, prefijo: str, claves) -> dict:
    """
    Recoge las casillas `prefijo-clave` que traigan algo.

    Las vacías no se guardan: un diccionario lleno de cadenas vacías ocupa
    sitio, se exporta y se lee como «se preguntó y no había», que no es lo
    mismo que «no se preguntó».
    """
    recogido = {}
    for clave in claves:
        valor = (datos.get(f"{prefijo}-{clave}") or "").strip()
        if valor:
            recogido[clave] = valor
    return recogido


def registrar_persona(datos: dict, usuario=None) -> Expediente:
    """
    Da de alta a una persona y abre su expediente.

    Es la salida al callejón que dejaba la búsqueda: cuando una cédula no está
    ni en la base local ni en la institucional, la pantalla ofrecía registrarla
    como externa pero no había por dónde hacerlo.

    Solo tres datos son obligatorios —cédula, nombres y apellidos—, que son los
    que identifican a la persona; el resto se guarda si viene y se deja en
    blanco si no. Obligar a más en el mostrador llevaría a inventarlo.

    No valida la cédula aquí: `Persona.save()` aplica el módulo 10 sobre los
    documentos de tipo cédula, así que la comprobación vive en un solo sitio.
    """
    from apps.academico import mapping

    from .campos import GRUPOS_JSON

    cedula = normalizar_cedula(datos.get("cedula", ""))
    if Persona.objects.filter(cedula=cedula).exists():
        raise ValidationError(f"Ya existe una persona registrada con la cédula {cedula}.")

    if not (datos.get("nombres") or "").strip() or not (datos.get("apellidos") or "").strip():
        raise ValidationError("Nombres y apellidos son obligatorios.")

    # Antes de escribir nada: `ATOMIC_REQUESTS` envuelve la petición entera y
    # validar a medias dejaría el rechazo dentro de la misma transacción.
    porcentaje = _porcentaje_de_discapacidad(datos.get("discapacidad_porcentaje"))

    with transaction.atomic():
        persona = Persona.objects.create(
            cedula=cedula,
            tipo_documento=datos.get("tipo_documento") or "cedula",
            nombres=datos["nombres"].strip(),
            apellidos=datos["apellidos"].strip(),
            fecha_nacimiento=datos.get("fecha_nacimiento") or None,
            sexo=datos.get("sexo", ""),
            genero=datos.get("genero", ""),
            identidad_orientacion_sexual=datos.get("identidad_orientacion_sexual", ""),
            tipo_vinculo=datos.get("tipo_vinculo") or Persona.TipoVinculo.EXTERNO,
            correo_institucional=datos.get("correo_institucional", ""),
            correo_personal=datos.get("correo_personal", ""),
            telefono=datos.get("telefono", ""),
            celular=datos.get("celular", ""),
            **{
                atributo: _grupo_json(datos, prefijo, mapping.PERSONA_JSONB[atributo])
                for prefijo, atributo, _titulo in GRUPOS_JSON
            },
            creado_por=usuario,
        )
        expediente = obtener_o_crear_expediente(persona, usuario)

        # Salud básica: vive en el expediente, no en la persona.
        cambios = []
        for campo, valor in (
            ("grupo_sanguineo", (datos.get("grupo_sanguineo") or "").strip()),
            ("discapacidad_tipo", (datos.get("discapacidad_tipo") or "").strip()),
            ("discapacidad_porcentaje", porcentaje),
        ):
            if valor not in (None, ""):
                setattr(expediente, campo, valor)
                cambios.append(campo)
        if cambios:
            expediente.save(update_fields=cambios)
        return expediente


def registrar_alerta(
    expediente: Expediente, tipo: str, descripcion: str, *, usuario=None
) -> AlertaClinica:
    """
    Registra (o reactiva) una alerta clínica sobre el expediente.

    Antes solo la crearba la carga académica masiva o el panel de
    administración: no había manera de que un profesional marcara, por
    ejemplo, una gestación o una enfermedad catastrófica detectada en consulta.

    `AlertaClinica` es "visible en todo el expediente" por diseño —el modelo
    ya lo dice—: una alergia debe verla Farmacia, una NEE debe verla
    Psicopedagogía. No es contenido clínico narrativo, es una bandera, y por
    eso no compromete el sello de Psicología: lo que el sello protege es la
    evolución y el contenido de la atención, no la existencia de una bandera.

    Idempotente por (expediente, tipo, descripción): registrar la misma alerta
    dos veces la reactiva en vez de duplicarla.
    """
    tipo_valido = {c for c, _ in AlertaClinica.Tipo.choices}
    if tipo not in tipo_valido:
        raise ValidationError(f"Tipo de alerta no reconocido: {tipo}.")
    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise ValidationError("La alerta necesita una descripción.")

    alerta, creada = AlertaClinica.objects.get_or_create(
        expediente=expediente,
        tipo=tipo,
        descripcion=descripcion,
        defaults={
            "activa": True,
            "creado_por": usuario,
            # Lo que registra un profesional queda marcado como suyo: una
            # recarga de la base institucional puede apagar lo que ella misma
            # declaró, nunca lo que alguien comprobó en consulta.
            "origen": AlertaClinica.Origen.PROFESIONAL,
        },
    )
    cambios = []
    if not creada and not alerta.activa:
        alerta.activa = True
        cambios.append("activa")
    if not creada and alerta.origen != AlertaClinica.Origen.PROFESIONAL:
        # La declaró la matrícula y ahora la confirma un profesional: pasa a ser
        # suya, y la siguiente carga ya no la apaga.
        alerta.origen = AlertaClinica.Origen.PROFESIONAL
        cambios.append("origen")
    if cambios:
        alerta.save(update_fields=cambios)
    return alerta


def desactivar_alerta(alerta: AlertaClinica) -> AlertaClinica:
    """Retira una alerta de la vista del expediente sin borrar su historial."""
    if alerta.activa:
        alerta.activa = False
        alerta.save(update_fields=["activa"])
    return alerta


def resolver_por_cedula(cedula: str, usuario=None):
    """
    Resuelve una cédula a (persona, expediente, datos_institucionales).

    Si la persona no está en la base local, consulta el proveedor académico
    (fase 1: réplica de la ficha; fase 2: SGA). Devuelve None si no existe en
    ninguna fuente (candidata a registro manual como externo).
    """
    persona = Persona.objects.filter(cedula=cedula).first()
    datos = get_provider().consultar_persona(cedula)

    if persona is None and datos is None:
        return None

    if persona is None and datos is not None:
        persona = Persona.objects.create(
            cedula=datos["cedula"],
            nombres=datos.get("nombres", ""),
            apellidos=datos.get("apellidos", ""),
            tipo_vinculo=datos.get("tipo_vinculo", Persona.TipoVinculo.EXTERNO),
            correo_institucional=datos.get("email_institucional", ""),
            creado_por=usuario,
        )

    expediente = obtener_o_crear_expediente(persona, usuario) if persona else None
    return {"persona": persona, "expediente": expediente, "institucional": datos}


def construir_snapshot(persona: Persona) -> dict:
    """
    Congela los datos institucionales vigentes para guardarlos en la atención
    (informe 7.5): así los reportes históricos reflejan la carrera/período del
    momento de la atención aunque luego cambien.
    """
    datos = get_provider().consultar_persona(persona.cedula) or {}
    return {
        "facultad": datos.get("facultad", ""),
        "carrera": datos.get("carrera", ""),
        "ciclo": datos.get("ciclo", ""),
        "modalidad": datos.get("modalidad", ""),
        "jornada": datos.get("jornada", ""),
        "estado": datos.get("estado", ""),
        "periodo": datos.get("periodo", ""),
        "tipo_vinculo": persona.tipo_vinculo,
    }


# ============================================================
# Alta en lote por cédulas
# ============================================================

# Lo que separa una cédula de la siguiente cuando se pegan varias: salto de
# línea, coma, punto y coma, tabulador o espacio. Se aceptan todas a la vez
# porque quien pega una lista la trae de donde la trae —una columna de Excel,
# un correo, un oficio— y no tiene por qué reformatearla.
SEPARADORES = "\n\r\t,;. "

# Cota del lote. No es un capricho: cada cédula consulta el padrón y puede
# abrir un expediente, y una petición web que haga eso diez mil veces se cae
# por tiempo dejando el trabajo a medias y sin decir por dónde iba.
MAXIMO_POR_LOTE = 300


def separar_cedulas(texto: str) -> list[str]:
    """
    Parte un bloque de texto en cédulas, conservando el orden y sin repetir.

    Se conserva el orden porque el informe de resultados se lee contra la lista
    que la persona pegó: reordenarlo obligaría a buscar cada línea. Y no se
    repiten porque la misma cédula dos veces es un error de copiado, no una
    orden de registrar a alguien dos veces.
    """
    if not texto:
        return []
    for separador in SEPARADORES:
        texto = texto.replace(separador, "\n")
    vistas: set[str] = set()
    ordenadas = []
    for parte in texto.split("\n"):
        parte = parte.strip()
        if parte and parte not in vistas:
            vistas.add(parte)
            ordenadas.append(parte)
    return ordenadas


def registrar_lote_de_cedulas(texto: str, usuario=None) -> dict:
    """
    Resuelve una lista de cédulas de una vez y devuelve qué pasó con cada una.

    Cada cédula se procesa por separado y a propósito: una mal digitada en
    medio de doscientas no puede tumbar el lote entero ni dejarlo a medias sin
    decir dónde se cortó. Por eso aquí NO hay una transacción que envuelva todo.

    Se admiten nueve o diez dígitos. Con nueve se antepone el cero que Excel
    suele comerse al tratar la cédula como número —lo hace `normalizar_cedula`,
    que ya existía—, y el resultado se informa para que quien lo lea vea en qué
    se convirtió lo que pegó.

    Estados posibles por cédula:

    - `abierto`     el expediente se creó ahora.
    - `existente`   ya lo tenía; no se toca nada.
    - `invalida`    no pasa el módulo 10 ecuatoriano.
    - `desconocida` válida, pero no está en la base institucional.

    Una cédula desconocida NO se registra con nombre en blanco. Un expediente
    sin nombre no identifica a nadie y ensucia el padrón para siempre; se
    informa con un enlace para completar el alta a mano. Es la misma regla de
    siempre: ausencia de dato no es prueba de ausencia, y tampoco licencia para
    inventarlo.
    """
    from apps.academico.validators import validar_cedula_ecuatoriana

    entradas = separar_cedulas(texto)
    if not entradas:
        raise ValidationError("No se reconoció ninguna cédula en lo que escribió.")
    if len(entradas) > MAXIMO_POR_LOTE:
        raise ValidationError(
            f"El lote trae {len(entradas)} cédulas y el máximo por tanda es "
            f"{MAXIMO_POR_LOTE}. Divídalo y repita."
        )

    filas = []
    for original in entradas:
        cedula = normalizar_cedula(original)
        fila = {"original": original, "cedula": cedula, "expediente": None, "persona": None}

        if not validar_cedula_ecuatoriana(cedula):
            fila["estado"] = "invalida"
            fila["detalle"] = (
                "No pasa el módulo 10 ecuatoriano."
                if cedula.isdigit()
                else "No es un número de cédula."
            )
            filas.append(fila)
            continue

        # Antes de resolver, porque `resolver_por_cedula` crea el expediente si
        # falta: preguntar después ya no distinguiría lo que había de lo nuevo.
        ya_tenia = Expediente.objects.filter(persona__cedula=cedula).exists()
        resultado = resolver_por_cedula(cedula, usuario=usuario)

        if resultado is None:
            fila["estado"] = "desconocida"
            fila["detalle"] = "No consta en la base institucional; regístrela a mano."
        else:
            fila["persona"] = resultado["persona"]
            fila["expediente"] = resultado["expediente"]
            fila["estado"] = "existente" if ya_tenia else "abierto"
            fila["detalle"] = ""
        filas.append(fila)

    resumen = {estado: 0 for estado in ("abierto", "existente", "invalida", "desconocida")}
    for fila in filas:
        resumen[fila["estado"]] += 1

    # Fuera de cualquier bloque atómico y después del trabajo, no antes:
    # registrar y luego abortar dentro de la misma transacción revierte el
    # propio registro. Ya nos costó caro dos veces (firma, portal).
    if usuario is not None and usuario.is_authenticated:
        from apps.auditoria.models import LogAuditoria

        LogAuditoria.objects.create(
            usuario=usuario,
            rol_activo=getattr(usuario, "rol_principal", ""),
            accion=LogAuditoria.Accion.CREATE,
            modulo="expediente",
            entidad="Expediente",
            entidad_id="lote",
            detalle={"total": len(filas), **resumen},
        )

    return {"filas": filas, "resumen": resumen, "total": len(filas)}


# ============================================================
# Ajustes por servicio
# ============================================================

# Las que un servicio NO puede ajustar, y por qué. Se nombran aquí para que el
# mensaje de rechazo diga la razón y no solo que no se puede.
NO_AJUSTABLES = {
    "genero": "el género",
    "identidad_orientacion_sexual": "la identidad u orientación sexual",
}


def registrar_ajuste(expediente, servicio, variable: str, valor: str, *, usuario=None, nota=""):
    """
    Anota, para ESTE servicio, un valor distinto del que trae la matrícula.

    No toca la base institucional: es la fuente para el resto del sistema y
    nadie autorizó a reescribirla desde una consulta. Lo que cambia es lo que
    este servicio ve y reporta.

    Se rechaza el ajuste del género y de la identidad u orientación sexual: son
    declaraciones de la persona sobre sí misma, y que un servicio las
    «corrigiera» sería asignarle una identidad. Se cambian donde se declaran.

    Idempotente por (expediente, servicio, variable): volver a ajustar la misma
    variable reemplaza el valor, no acumula filas.
    """
    from apps.auditoria.models import LogAuditoria

    from .models import AjusteDeServicio

    if variable in NO_AJUSTABLES:
        raise ValidationError(
            f"No se puede ajustar {NO_AJUSTABLES[variable]} desde un servicio: "
            "lo declara la propia persona. Corríjalo en su ficha o en el portal."
        )
    if variable not in {c for c, _ in AjusteDeServicio.Variable.choices}:
        raise ValidationError(f"Variable no ajustable: {variable}.")

    valor = (valor or "").strip()
    if not valor:
        raise ValidationError("El ajuste necesita un valor.")

    if variable == AjusteDeServicio.Variable.DISCAPACIDAD_PORCENTAJE:
        # Mismo criterio que el alta: un porcentaje ilegible se rechaza aquí y
        # no en forma de error de base de datos más adelante.
        _porcentaje_de_discapacidad(valor)

    ajuste, _ = AjusteDeServicio.objects.update_or_create(
        expediente=expediente,
        servicio=servicio,
        variable=variable,
        defaults={"valor": valor, "nota": (nota or "").strip(), "creado_por": usuario},
    )

    LogAuditoria.objects.create(
        usuario=usuario,
        rol_activo=getattr(usuario, "rol_principal", ""),
        accion=LogAuditoria.Accion.UPDATE,
        modulo="expediente",
        entidad="AjusteDeServicio",
        entidad_id=str(ajuste.pk),
        expediente_id=expediente.pk,
        detalle={"servicio": servicio.codigo, "variable": variable, "valor": valor},
    )
    return ajuste


def quitar_ajuste(expediente, servicio, variable: str, *, usuario=None) -> bool:
    """
    Deshace el ajuste y devuelve la variable a lo que dice la matrícula.

    Que se pueda volver atrás es lo que hace seguro ajustar: sin esto, una
    corrección equivocada quedaría fija para siempre en ese servicio.
    """
    from apps.auditoria.models import LogAuditoria

    from .models import AjusteDeServicio

    borrados, _ = AjusteDeServicio.objects.filter(
        expediente=expediente, servicio=servicio, variable=variable
    ).delete()
    if borrados:
        LogAuditoria.objects.create(
            usuario=usuario,
            rol_activo=getattr(usuario, "rol_principal", ""),
            accion=LogAuditoria.Accion.SOFT_DELETE,
            modulo="expediente",
            entidad="AjusteDeServicio",
            entidad_id=f"{expediente.pk}:{servicio.codigo}:{variable}",
            expediente_id=expediente.pk,
            detalle={"servicio": servicio.codigo, "variable": variable},
        )
    return bool(borrados)


def verificar_profesional_del_servicio(perfil, servicio) -> None:
    """
    Un profesional abre atenciones en SU servicio, no en el de otro.

    Ninguno de los servicios lo comprobaba: `crear_ficha`, `abrir_consulta` y
    compañía recibían un `PerfilProfesional` cualquiera y lo grababan como
    tratante. Sobre Psicología eso no era una incoherencia de datos sino una
    escalada: `rbac.puede_ver_atencion` concede acceso al tratante ANTES de
    mirar si el servicio es confidencial —«el propio profesional que la
    realizó siempre puede verla»—, así que quien se nombraba tratante entraba
    al servicio sellado por la puerta principal.

    Va en la capa de servicios y no solo en las vistas porque por aquí pasan la
    pantalla, la API y lo que se escriba mañana. La pantalla de Psicología ya
    lo comprobaba por su cuenta; la API no, y ese fue todo el agujero.
    """
    from django.core.exceptions import ValidationError

    if perfil is None:
        raise ValidationError("Se requiere un perfil profesional para abrir la atención.")
    if not perfil.servicios.filter(pk=servicio.pk).exists():
        raise ValidationError(
            f"No pertenece al servicio {servicio.nombre}: no puede abrir una atención en él."
        )
