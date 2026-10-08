"""Tablero de gestión. Solo roles directivos; solo agregados."""

import csv
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.core.mensajes import detalle_de_error
from apps.core.models import Servicio
from apps.core.pdf import render_pdf
from apps.usuarios import rbac
from apps.usuarios.models import Rol
from apps.usuarios.rbac import servicios_del_usuario

from . import services

ROLES_TABLERO = {Rol.ADMIN_GENERAL, Rol.DIRECTOR, Rol.COORDINADOR}


def _solo_directivos(user):
    if user.rol_principal not in ROLES_TABLERO:
        raise PermissionDenied("El tablero de gestión es para la Dirección y las Coordinaciones.")


def _rango(request):
    desde = hasta = None
    try:
        if request.GET.get("desde"):
            desde = datetime.strptime(request.GET["desde"], "%Y-%m-%d").date()
        if request.GET.get("hasta"):
            hasta = datetime.strptime(request.GET["hasta"], "%Y-%m-%d").date()
    except ValueError:
        pass
    return desde, hasta


@login_required
def tablero(request):
    _solo_directivos(request.user)
    desde, hasta = _rango(request)
    return render(
        request,
        "reportes/tablero.html",
        {"datos": services.tablero_general(desde, hasta), "desde": desde, "hasta": hasta},
    )


@login_required
def exportar_pdf(request):
    """
    El tablero como documento formal, con el membrete institucional.

    El CSV sirve para seguir trabajando los datos; este PDF es el que se
    archiva o se entrega. Los conteos llegan ya suprimidos desde `services`, así
    que el documento no puede publicar una cifra que la pantalla oculta.
    """
    _solo_directivos(request.user)
    desde, hasta = _rango(request)

    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="TableroGeneral",
        entidad_id="pdf",
        detalle={"desde": str(desde or ""), "hasta": str(hasta or "")},
    )

    pdf = render_pdf(
        "reportes/tablero_pdf.html",
        {
            "datos": services.tablero_general(desde, hasta),
            "desde": desde,
            "hasta": hasta,
            "k_minimo": services.K_MINIMO,
        },
    )
    respuesta = HttpResponse(pdf, content_type="application/pdf")
    nombre = f"reporte-gestion-{timezone.localdate():%Y%m%d}.pdf"
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@login_required
def exportar_csv(request):
    """Atenciones por servicio en CSV. La exportación queda auditada."""
    _solo_directivos(request.user)
    desde, hasta = _rango(request)
    filas = services.atenciones_por_servicio(desde, hasta)

    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="TableroGeneral",
        entidad_id="csv",
        detalle={"desde": str(desde or ""), "hasta": str(hasta or "")},
    )
    respuesta = HttpResponse(content_type="text/csv")
    respuesta["Content-Disposition"] = 'attachment; filename="atenciones_por_servicio.csv"'
    w = csv.writer(respuesta)
    w.writerow(["servicio", "atenciones", "pacientes_distintos"])
    for f in filas:
        w.writerow([f["servicio"], f["total"], f["pacientes"]])
    return respuesta


def _mis_servicios(user):
    """
    Los servicios del profesional, o 403 si no tiene ninguno.

    El informe demográfico es distinto del tablero: aquí no hace falta ser
    Dirección, basta con pertenecer al servicio que se va a informar —es el
    mismo contenido que ya se ve atención por atención, solo que sumado—.
    """
    mis = Servicio.objects.filter(pk__in=servicios_del_usuario(user))
    if not mis:
        raise PermissionDenied("Su usuario no tiene servicios asignados.")
    return mis


def _servicio_o_403(request, mis_servicios):
    servicio_id = request.GET.get("servicio") or mis_servicios[0].pk
    servicio = mis_servicios.filter(pk=servicio_id).first()
    if servicio is None:
        raise PermissionDenied("Ese servicio no le corresponde.")
    return servicio


ANEXOS = {"nomina": "Nómina de personas atendidas", "evidencias": "Evidencia de los valores"}


def _eleccion(request) -> dict:
    """
    Qué pidió incluir el profesional: variables, anexos, columnas e identidad.

    `elegir=1` es lo que distingue «no elegí nada» de «desmarqué todo»: un
    formulario no envía las casillas sin marcar, así que sin ese testigo un
    informe al que se le quitaron todas las variables llegaría aquí idéntico a
    uno recién abierto, y saldría con las nueve.

    La identidad se protege salvo que se pida lo contrario, y no al revés: la
    opción por defecto de un documento que va a salir de la Unidad tiene que
    ser la que no identifica a nadie.
    """
    from . import anexos as modulo_anexos

    eligio = request.GET.get("elegir") == "1"
    variables = request.GET.getlist("variables") if eligio else None
    columnas = request.GET.getlist("columnas") if eligio else None
    pedidos = [a for a in request.GET.getlist("anexos") if a in ANEXOS]
    proteger = request.GET.get("identidad") != "mostrar"
    elegidas, _retiradas = modulo_anexos.normalizar_columnas(columnas, proteger)
    return {
        "variables": services.normalizar_variables(variables),
        "anexos": pedidos,
        "columnas": elegidas,
        "columnas_pedidas": columnas,
        # Lo que se queda marcado en el formulario es lo que se PIDIÓ, no lo que
        # sobrevivió a la protección: una casilla que se desmarca sola al enviar
        # parece un fallo. Que la columna no salió se dice al pie del anexo,
        # nombrándola.
        "columnas_marcadas": elegidas if columnas is None else columnas,
        "proteger": proteger,
    }


def _anexos_de(servicio, desde, hasta, eleccion: dict) -> dict:
    """
    Los anexos pedidos, o el motivo por el que no salen.

    Un servicio confidencial no puede anexar la nómina, y `anexos` lo dice
    lanzando: aquí se traduce a un aviso en pantalla en vez de a un error,
    porque el informe agregado sí es legítimo y debe seguir generándose.
    """
    from . import anexos as modulo_anexos

    resultado = {"nomina": None, "evidencias": None, "aviso": ""}
    if not eleccion["anexos"]:
        return resultado
    comunes = {
        "columnas": eleccion["columnas_pedidas"],
        "proteger": eleccion["proteger"],
    }
    try:
        if "nomina" in eleccion["anexos"]:
            resultado["nomina"] = modulo_anexos.nomina(servicio, desde, hasta, **comunes)
        if "evidencias" in eleccion["anexos"]:
            resultado["evidencias"] = modulo_anexos.evidencias(
                servicio, desde, hasta, variables=eleccion["variables"], **comunes
            )
    except ValidationError as exc:
        resultado["aviso"] = detalle_de_error(exc, "No se pudo generar el anexo.")
    return resultado


@login_required
def informe_servicio(request):
    """Perfil demográfico de las atenciones de un servicio propio, por fechas."""
    from . import anexos as modulo_anexos

    mis_servicios = _mis_servicios(request.user)
    servicio = _servicio_o_403(request, mis_servicios)
    desde, hasta = _rango(request)
    eleccion = _eleccion(request)
    datos = services.informe_estadistico(servicio, desde, hasta, eleccion["variables"])
    return render(
        request,
        "reportes/informe_servicio.html",
        {
            "datos": datos,
            "servicios": mis_servicios,
            "servicio": servicio,
            "desde": desde,
            "hasta": hasta,
            "eleccion": eleccion,
            "anexos": _anexos_de(servicio, desde, hasta, eleccion),
            # Lo que la pantalla ofrece marcar, derivado de donde se calcula.
            "variables_disponibles": services.VARIABLES.items(),
            "anexos_disponibles": ANEXOS.items(),
            "columnas_disponibles": modulo_anexos.COLUMNAS.items(),
            "confidencial": servicio.codigo in rbac.SERVICIOS_CONFIDENCIALES,
            "parametros": _parametros(request),
        },
    )


def _parametros(request) -> str:
    """Lo elegido, listo para colgar de un enlace (PDF, Excel) sin perderlo."""
    from urllib.parse import urlencode

    campos = [
        "servicio",
        "desde",
        "hasta",
        "elegir",
        "variables",
        "anexos",
        "columnas",
        "identidad",
    ]
    datos = {c: request.GET.getlist(c) for c in campos if request.GET.getlist(c)}
    return urlencode(datos, doseq=True)


@login_required
def informe_servicio_pdf(request):
    """El informe demográfico como documento formal, con membrete institucional."""
    mis_servicios = _mis_servicios(request.user)
    servicio = _servicio_o_403(request, mis_servicios)
    desde, hasta = _rango(request)
    eleccion = _eleccion(request)
    datos = services.informe_estadistico(servicio, desde, hasta, eleccion["variables"])
    anexos = _anexos_de(servicio, desde, hasta, eleccion)

    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="InformeEstadistico",
        entidad_id=servicio.codigo,
        # Qué llevaba el documento queda en el log: un informe con la nómina y
        # sin proteger la identidad es una salida de datos personales, y
        # distinguirla después de una tabla de porcentajes es justo lo que la
        # bitácora tiene que permitir.
        detalle={
            "desde": str(desde or ""),
            "hasta": str(hasta or ""),
            "variables": eleccion["variables"],
            "anexos": eleccion["anexos"],
            "identidad_protegida": eleccion["proteger"],
        },
        servicio=servicio.codigo,
    )

    pdf = render_pdf(
        "reportes/informe_servicio_pdf.html",
        {"datos": datos, "anexos": anexos, "eleccion": eleccion},
    )
    respuesta = HttpResponse(pdf, content_type="application/pdf")
    nombre = f"informe-demografico-{servicio.codigo}-{timezone.localdate():%Y%m%d}.pdf"
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@login_required
def informe_servicio_xlsx(request):
    """
    La nómina del informe en Excel, con la línea gráfica de la Universidad.

    El PDF es el documento que se archiva; esto es la misma nómina para seguir
    trabajándola. No se exporta el desglose de porcentajes —eso ya está en el
    PDF y en pantalla—: lo que no se puede hacer con un PDF es cruzar la lista
    con otra, y para eso hace falta la tabla.
    """
    from apps.core.xlsx import libro_institucional, nombre_de_archivo

    from . import anexos as modulo_anexos

    mis_servicios = _mis_servicios(request.user)
    servicio = _servicio_o_403(request, mis_servicios)
    desde, hasta = _rango(request)
    eleccion = _eleccion(request)

    try:
        nomina = modulo_anexos.nomina(
            servicio,
            desde,
            hasta,
            columnas=eleccion["columnas_pedidas"],
            proteger=eleccion["proteger"],
        )
    except ValidationError as exc:
        messages.error(request, detalle_de_error(exc, "No se pudo generar la nómina."))
        return redirect(f"{reverse('reportes:informe_servicio')}?{_parametros(request)}")

    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="InformeEstadistico",
        entidad_id=servicio.codigo,
        detalle={
            "formato": "xlsx",
            "anexo": "nomina",
            "filas": nomina["total"],
            "identidad_protegida": eleccion["proteger"],
        },
        servicio=servicio.codigo,
    )

    libro = libro_institucional(
        titulo="Nómina de personas atendidas",
        subtitulo=_subtitulo_de_nomina(nomina["total"], desde, hasta, servicio.codigo),
        encabezados=nomina["encabezados"],
        filas=nomina["filas"],
        nota_pie=_nota_de_nomina(nomina),
        nombre_hoja="Nómina",
    )
    return _respuesta_xlsx(libro, nombre_de_archivo("nomina", servicio=servicio.codigo))


def _subtitulo_de_nomina(cuantas, desde, hasta, servicio) -> str:
    """Cuenta PERSONAS, no atenciones: por eso no reutiliza `_subtitulo`."""
    partes = [f"{cuantas} {'persona atendida' if cuantas == 1 else 'personas atendidas'}"]
    partes.append(f"servicio: {servicio}")
    if desde or hasta:
        partes.append(f"del {desde or '…'} al {hasta or '…'}")
    partes.append(f"generado el {timezone.localtime():%d/%m/%Y %H:%M}")
    return " · ".join(partes)


def _nota_de_nomina(nomina: dict) -> str:
    """El pie que explica qué se retiró: una lista recortada en silencio miente."""
    if nomina["protegida"]:
        return (
            "Identidad protegida: no se reportan cédula, teléfono, correo "
            "institucional ni número de expediente. Cada fila se cita por su "
            "código. Documento con datos personales bajo custodia de la Unidad."
        )
    return (
        "Este anexo incluye datos identificativos de las personas atendidas. "
        "Custodia de la Unidad de Bienestar Universitario: no se difunde ni se "
        "comparte fuera del servicio que lo generó."
    )


@login_required
def exportar_hoja(request):
    """
    Vuelca el historial de atenciones a una hoja de Google compartida.

    Lo abre quien atiende, no la Dirección, y no es un olvido: el historial que
    se exporta es el que cada uno ve, y `rbac.atenciones_visibles` le devuelve
    cero a quien gobierna por separación de funciones. La Dirección tiene el
    tablero y su CSV de agregados.

    La pantalla dice, antes de pulsar nada, cuántas filas saldrían, cuántas se
    retienen por confidencialidad y qué implica compartir la hoja. Eso último
    importa: a partir del volcado SIBU no controla quién lo lee, no puede
    impedir que lo modifiquen y no puede revocarlo.
    """
    from . import exportacion

    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("La exportación del historial es para el personal de la Unidad.")

    desde, hasta = _rango(request)
    servicio = (request.GET.get("servicio") or "").strip()
    if servicio:
        # Se comprueba y se DICE: un archivo vacío sin explicación se lee como
        # un fallo del sistema.
        try:
            exportacion.verificar_exportable(servicio)
        except ValidationError as exc:
            raise PermissionDenied("; ".join(exc.messages)) from exc

    formato = request.GET.get("formato")
    if formato in ("csv", "xlsx"):
        return _historial_archivo(request, desde, hasta, servicio, formato)

    proveedor = exportacion.get_proveedor()
    contexto = {
        "servicio": servicio,
        "resumen": exportacion.resumen_de_exportacion(request.user, desde, hasta, servicio),
        "encabezados": exportacion.ENCABEZADOS,
        "desde": desde,
        "hasta": hasta,
        "proveedor": proveedor,
        "disponible": proveedor.disponible(),
        "motivo": "" if proveedor.disponible() else proveedor.motivo_no_disponible(),
    }

    if request.method == "POST":
        try:
            hoja_id = exportacion.id_de_hoja(request.POST.get("enlace", ""))
            filas = exportacion.historial(request.user, desde, hasta, servicio)
            url = proveedor.volcar(
                hoja_id,
                exportacion.ENCABEZADOS,
                [[fila[c] for c in exportacion.ENCABEZADOS] for fila in filas],
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            # Sacar el historial de la Unidad es de lo que más falta hace poder
            # revisar después: quién, cuándo, cuántas filas y a qué hoja.
            LogAuditoria.objects.create(
                usuario=request.user,
                accion=LogAuditoria.Accion.EXPORT,
                modulo="reportes",
                entidad="HistorialAtenciones",
                entidad_id=hoja_id,
                detalle={
                    "hoja": hoja_id,
                    "filas": len(filas),
                    "retenidas": contexto["resumen"]["retenidas_por_confidencialidad"],
                    "desde": str(desde or ""),
                    "hasta": str(hasta or ""),
                },
            )
            messages.success(request, f"{len(filas)} atención(es) volcadas en la hoja.")
            contexto["url_hoja"] = url

    return render(request, "reportes/exportar_hoja.html", contexto)


def _historial_archivo(request, desde, hasta, servicio, formato):
    """
    El mismo historial, descargado en vez de volcado, en CSV o en Excel.

    El Excel lleva la línea gráfica de la Universidad; el CSV existe para quien
    va a seguir procesando los datos con otra herramienta. Los dos traen
    exactamente las mismas filas y el mismo filtro: son la misma exportación
    por otro camino, no una puerta más ancha.
    """
    from apps.core.xlsx import libro_institucional, nombre_de_archivo

    from . import exportacion

    filas = exportacion.historial(request.user, desde, hasta, servicio)
    resumen = exportacion.resumen_de_exportacion(request.user, desde, hasta, servicio)
    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="HistorialAtenciones",
        entidad_id=servicio or "todos",
        servicio=servicio,
        detalle={
            "formato": formato,
            "filas": len(filas),
            "retenidas": resumen["retenidas_por_confidencialidad"],
            "servicio": servicio,
            "desde": str(desde or ""),
            "hasta": str(hasta or ""),
        },
    )

    matriz = [[fila[c] for c in exportacion.ENCABEZADOS] for fila in filas]
    if formato == "xlsx":
        return _respuesta_xlsx(
            libro_institucional(
                titulo="Historial de atenciones",
                subtitulo=_subtitulo(servicio, desde, hasta, len(filas)),
                encabezados=exportacion.ENCABEZADOS,
                filas=matriz,
                nota_pie=(
                    "Documento con datos personales de pacientes. Su custodia y "
                    "difusión quedan bajo responsabilidad de quien lo descargó. "
                    "No incluye contenido clínico ni atenciones de servicios "
                    "confidenciales."
                ),
            ),
            nombre_de_archivo("historial-atenciones", servicio=servicio),
        )

    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = (
        f'attachment; filename="historial-atenciones-{timezone.localdate()}.csv"'
    )
    # BOM: sin él, Excel en Windows abre el archivo en Latin-1 y parte las
    # tildes de «atención» y de los apellidos.
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(exportacion.ENCABEZADOS)
    for fila in matriz:
        escritor.writerow(fila)
    return respuesta


def _subtitulo(servicio, desde, hasta, cuantas) -> str:
    # «atención»/«atenciones» escrito a mano: el plural pierde la tilde, así
    # que ni `pluralize` ni un «(es)» pegado dan la palabra correcta.
    partes = [f"{cuantas} {'atención' if cuantas == 1 else 'atenciones'}"]
    if servicio:
        partes.append(f"servicio: {servicio}")
    if desde or hasta:
        partes.append(f"del {desde or '…'} al {hasta or '…'}")
    partes.append(f"generado el {timezone.localtime():%d/%m/%Y %H:%M}")
    return " · ".join(partes)


def _respuesta_xlsx(libro, nombre):
    import io

    memoria = io.BytesIO()
    libro.save(memoria)
    respuesta = HttpResponse(
        memoria.getvalue(),
        content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    )
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta
