"""
El resumen de la bandeja no puede contradecir a la tabla que tiene debajo.

Los cuatro tramos del resumen son los que produce `calcular_puntaje`, y una
ficha pre-poblada desde matrícula todavía no ha pasado por ahí: su estrato está
vacío. Con siete fichas así, la pantalla enseñaba **cuatro ceros** sobre una
tabla de siete filas. Cuatro ceros se leen como «no hay nada que hacer» y era
justo lo contrario: eran las siete que faltaba verificar, que es la cola de
trabajo del servicio.

La plantilla ya llevaba escrito el criterio —«un tramo ausente se lee como *no
lo hemos mirado*»— y el tramo ausente era precisamente ese.
"""

import pytest

from apps.expediente.tests.factories import crear_expediente
from apps.trabajo_social import selectors
from apps.trabajo_social.models import FichaSocioeconomica


def _ficha(cedula, estrato=""):
    return FichaSocioeconomica.objects.create(
        expediente=crear_expediente(cedula=cedula),
        version=1,
        vigente=True,
        origen="matricula",
        estrato=estrato,
    )


@pytest.mark.django_db
def test_las_fichas_sin_verificar_se_cuentan():
    _ficha("1101001004")
    _ficha("1102002001")
    _ficha("1103003008", estrato="Vulnerabilidad alta")

    resumen = {r["estrato"]: r["total"] for r in selectors.resumen_por_estrato()}

    assert resumen[selectors.SIN_VERIFICAR] == 2
    assert resumen["Vulnerabilidad alta"] == 1


@pytest.mark.django_db
def test_el_resumen_suma_todas_las_fichas_vigentes():
    """
    Lo que de verdad falló: el resumen sumaba cero mientras la tabla listaba
    siete. Ninguna ficha vigente puede quedarse fuera de todos los tramos.
    """
    for i, cedula in enumerate(["1101001004", "1102002001", "1103003008"]):
        _ficha(cedula, estrato="Extrema vulnerabilidad" if i == 0 else "")

    total_resumen = sum(r["total"] for r in selectors.resumen_por_estrato())

    assert total_resumen == FichaSocioeconomica.objects.filter(vigente=True).count()


@pytest.mark.django_db
def test_se_puede_filtrar_por_sin_verificar():
    """
    El valor del filtro no puede ser la cadena vacía: ahí significa «todos los
    estratos». En la base el estrato SÍ es la cadena vacía, y la traducción
    entre las dos cosas es lo que se comprueba aquí.
    """
    sin = _ficha("1101001004")
    _ficha("1103003008", estrato="Vulnerabilidad media")

    filtradas = list(selectors.casos(estrato=selectors.SIN_VERIFICAR))
    todas = list(selectors.casos(estrato=""))

    assert filtradas == [sin]
    assert len(todas) == 2


@pytest.mark.django_db
def test_sin_verificar_va_primero():
    """Es la cola de trabajo, no un tramo de vulnerabilidad."""
    assert selectors.resumen_por_estrato()[0]["estrato"] == selectors.SIN_VERIFICAR
    assert selectors.ESTRATOS_DEL_FILTRO[0] == selectors.SIN_VERIFICAR
