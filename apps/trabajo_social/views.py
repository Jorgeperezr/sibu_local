"""Interfaz web de Trabajo Social: bandeja del servicio y ficha versionada."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.usuarios.decorators import verificar_es_del_servicio

from . import campos, selectors, services
from .models import FichaSocioeconomica


def _fusionar(actual: dict, post, claves, prefijo: str) -> dict:
    """
    Combina lo que la pantalla muestra con lo que no.

    Antes se reconstruía el diccionario entero desde el formulario, y eso hacía
    dos daños a la vez. Las casillas salían vacías, así que pulsar «Registrar
    verificación» sin tocar nada dejaba los ingresos en `{}`: el puntaje caía a
    cero y el estudiante pasaba a «Extrema vulnerabilidad» sin que nadie hubiera
    afirmado tal cosa. Y las claves que la ficha de matrícula trae pero la
    pantalla no dibuja —«quién financia sus estudios», el detalle de una deuda—
    desaparecían sin dejar rastro.

    Ahora las casillas llegan rellenas: lo que se ve es lo que se guarda, y
    vaciar una sigue significando borrar ese dato, que es lo que el profesional
    esperaría. Lo que no se dibuja, se conserva.
    """
    resultado = {k: v for k, v in (actual or {}).items() if k not in claves}
    for clave in claves:
        valor = (post.get(f"{prefijo}-{clave}") or "").strip()
        if valor:
            resultado[clave] = valor
    return resultado


@login_required
def bandeja(request):
    """
    Los casos del servicio: qué expedientes tienen ficha y en qué estrato.

    Trabajo Social era el único de los nueve servicios sin bandeja. Su
    profesional iniciaba sesión y no tenía por dónde entrar a lo suyo: se
    llegaba a una ficha solo desde el expediente abierto en otro módulo, o
    tecleando la URL con el id a mano.
    """
    from django.core.paginator import Paginator

    servicio = get_object_or_404(Servicio, codigo="trabajo-social")
    verificar_es_del_servicio(request.user, servicio)

    texto = (request.GET.get("q") or "").strip()
    estrato = (request.GET.get("estrato") or "").strip()
    consulta = selectors.casos(texto, estrato)
    return render(
        request,
        "trabajo_social/bandeja.html",
        {
            "pagina": Paginator(consulta, 40).get_page(request.GET.get("pagina")),
            "q": texto,
            "estrato": estrato,
            "estratos": selectors.ESTRATOS_DEL_FILTRO,
            "resumen": selectors.resumen_por_estrato(),
            "total": consulta.count(),
            "minimo_texto": selectors.MINIMO_TEXTO,
        },
    )


@login_required
def ficha(request, expediente_id):
    """Ficha vigente + historial de versiones."""
    servicio = get_object_or_404(Servicio, codigo="trabajo-social")
    verificar_es_del_servicio(request.user, servicio)
    expediente = get_object_or_404(Expediente.objects.select_related("persona"), pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        raise PermissionDenied("Su usuario no tiene perfil profesional.")

    if request.method == "POST":
        try:
            if request.POST.get("accion") == "prepoblar":
                services.prepoblar_desde_matricula(expediente, usuario=request.user)
                messages.success(request, "Ficha v1 creada con los datos declarados en matrícula.")
            else:
                vigente = services.ficha_vigente(expediente)
                actual = vigente or FichaSocioeconomica()
                datos = {
                    "ingresos": _fusionar(
                        actual.ingresos, request.POST, [c for c, _ in campos.INGRESOS], "ingreso"
                    ),
                    "egresos": _fusionar(
                        actual.egresos, request.POST, [c for c, _ in campos.EGRESOS], "egreso"
                    ),
                    # `convivencia` trae de matrícula lo declarado sobre necesidad
                    # educativa especial y maltrato. Reemplazarla entera por el
                    # número de miembros borraba justamente eso.
                    "convivencia": {
                        **(actual.convivencia or {}),
                        "numero_miembros": request.POST.get("numero_miembros", "1"),
                    },
                }
                nueva = services.verificar_ficha(
                    expediente, datos, profesional=perfil, usuario=request.user
                )
                messages.success(
                    request,
                    f"Versión {nueva.version} registrada. "
                    f"Puntaje {nueva.puntaje} SBU — {nueva.estrato}. "
                    f"La versión anterior se conserva.",
                )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("trabajo_social:ficha", expediente_id=expediente_id)

    vigente = services.ficha_vigente(expediente)
    return render(
        request,
        "trabajo_social/ficha.html",
        {
            "expediente": expediente,
            "vigente": vigente,
            "historial": services.historial_fichas(expediente),
            "ingresos": _casillas(vigente, "ingresos", campos.INGRESOS),
            "egresos": _casillas(vigente, "egresos", campos.EGRESOS),
            "informativos": _informativos(vigente),
        },
    )


def _casillas(ficha, atributo: str, catalogo) -> list[dict]:
    """Las casillas del formulario, cada una con el valor que hoy tiene."""
    guardado = getattr(ficha, atributo, None) or {}
    return [
        {"clave": clave, "etiqueta": etiqueta, "valor": guardado.get(clave, "")}
        for clave, etiqueta in catalogo
    ]


def _informativos(ficha) -> list[dict]:
    """
    Lo que el estudiante declaró en matrícula y aquí solo se lee.

    Estaba guardado desde la carga y no se mostraba en ninguna pantalla, así que
    en la práctica el profesional volvía a preguntar lo ya preguntado.
    """
    if ficha is None:
        return []
    grupos = []
    for atributo, titulo in campos.GRUPOS_INFORMATIVOS:
        contenido = getattr(ficha, atributo, None) or {}
        filas = [
            {"etiqueta": campos.rotular(clave), "valor": valor}
            for clave, valor in contenido.items()
            # `numero_miembros` tiene su propia casilla editable arriba: repetirlo
            # aquí como dato de solo lectura haría dudar de cuál manda.
            if valor not in (None, "", {}) and clave != "numero_miembros"
        ]
        if filas:
            grupos.append({"titulo": titulo, "filas": filas})
    return grupos
