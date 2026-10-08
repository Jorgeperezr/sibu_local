"""Pantalla de consulta de la bitácora."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.utils.http import urlencode

from . import selectors


@login_required
def bitacora(request):
    """
    Quién hizo qué, cuándo y sobre qué.

    Se registraba todo y no había dónde leerlo: la única vía era el shell o el
    panel de Django. Una bitácora que nadie puede consultar no rinde cuentas.

    Quién entra: gobierno —Dirección, Coordinación, administración— y los
    servicios confidenciales sobre SUS PROPIAS entradas, para poder auditarse.
    Un profesional corriente no: recorrer la bitácora entera diría quién pasó
    por cada servicio, que es contenido por agregación.
    """
    if not _puede_consultar(request.user):
        raise PermissionDenied("La bitácora es de consulta restringida.")

    filtros = {c: (request.GET.get(c) or "").strip() for c in selectors.FILTROS}
    filtros = {c: v for c, v in filtros.items() if v}
    desde = parse_date(request.GET.get("desde") or "")
    hasta = parse_date(request.GET.get("hasta") or "")

    consulta = selectors.bitacora(request.user, filtros=filtros, desde=desde, hasta=hasta)
    pagina = Paginator(consulta, 50).get_page(request.GET.get("pagina"))

    return render(
        request,
        "auditoria/bitacora.html",
        {
            "pagina": pagina,
            # Las filas ya traen resuelto qué se puede ver de cada registro: la
            # plantilla no recibe el expediente de una entrada velada, así que
            # no puede imprimirlo por descuido.
            "filas": selectors.filas_para(request.user, pagina.object_list),
            "opciones": selectors.opciones_de_filtro(request.user),
            "activos": filtros,
            "desde": request.GET.get("desde", ""),
            "hasta": request.GET.get("hasta", ""),
            "arrastre": urlencode(
                {k: v for k, v in ({**filtros, "desde": desde, "hasta": hasta}).items() if v}
            ),
            "total": consulta.count(),
        },
    )


def _puede_consultar(usuario) -> bool:
    from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES

    if selectors._puede_gobernar(usuario):
        return True
    # Un servicio confidencial se audita a sí mismo: nadie de fuera puede
    # revisar su trabajo, así que sin esto quedaría sin control ninguno.
    return bool(selectors._codigos_de_servicio(usuario) & SERVICIOS_CONFIDENCIALES)
