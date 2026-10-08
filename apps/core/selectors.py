"""Consultas de lectura de core."""

from __future__ import annotations

# Qué capítulos del catálogo CIE-10 ve cada servicio al diagnosticar.
# Medicina es atención primaria general: ve todo salvo lo que es propio de
# otro servicio, en vez de una lista aparte que hubiera que mantener en dos
# sitios cada vez que se agregue un capítulo nuevo.
CAPITULOS_EXCLUIDOS_DE_MEDICINA = {"XI. Odontología", "V. Psicopedagógico", "XXI. Trabajo social"}

CAPITULOS_POR_SERVICIO = {
    "odontologia": {"XI. Odontología"},
    "psicologia": {"V. Salud mental", "V. Psicopedagógico"},
    "psicopedagogia": {"V. Psicopedagógico"},
    "trabajo-social": {"XXI. Trabajo social"},
}


def diagnosticos_por_servicio(codigo_servicio: str):
    """
    El catálogo CIE-10 que corresponde a un servicio.

    Medicina ve el catálogo completo salvo los capítulos propios de otro
    servicio (Odontología, Psicopedagogía, Trabajo Social). Los demás
    servicios ven solo su subconjunto: Odontología no necesita elegir entre
    cientos de códigos de salud mental, ni Psicología entre los dentales.
    """
    from .models import CIE10

    if codigo_servicio == "medicina":
        return CIE10.objects.exclude(capitulo__in=CAPITULOS_EXCLUIDOS_DE_MEDICINA).order_by(
            "capitulo", "codigo"
        )

    capitulos = CAPITULOS_POR_SERVICIO.get(codigo_servicio)
    if not capitulos:
        return CIE10.objects.none()
    return CIE10.objects.filter(capitulo__in=capitulos).order_by("capitulo", "codigo")
