"""Pruebas de la ficha socioeconómica versionada y visitas domiciliarias."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.trabajo_social import services
from apps.trabajo_social.models import FichaSocioeconomica


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    ts, _ = Servicio.objects.get_or_create(
        codigo="trabajo-social", defaults={"nombre": "Trabajo Social", "seccion": est["salud"]}
    )
    _, trabajador = crear_profesional("ts", ts, ts.seccion)
    exp = crear_expediente(cedula="1104567894")
    exp.persona.residencia_actual = {"canton": "Loja", "tipo": "arrendada"}
    exp.persona.procedencia = {"canton": "Saraguro"}
    exp.persona.save()
    return {"est": est, "ts": ts, "trabajador": trabajador, "exp": exp}


@pytest.mark.django_db
def test_prepoblar_desde_matricula(escenario):
    ficha = services.prepoblar_desde_matricula(escenario["exp"])
    assert ficha.version == 1
    assert ficha.vigente is True
    assert ficha.origen == FichaSocioeconomica.Origen.MATRICULA
    assert ficha.vivienda_estudiante["canton"] == "Loja"
    assert ficha.vivienda_familiar["canton"] == "Saraguro"


@pytest.mark.django_db
def test_no_prepoblar_dos_veces(escenario):
    services.prepoblar_desde_matricula(escenario["exp"])
    with pytest.raises(ValidationError, match="ya tiene una ficha"):
        services.prepoblar_desde_matricula(escenario["exp"])


@pytest.mark.django_db
def test_verificar_crea_version_nueva_sin_borrar_la_anterior(escenario):
    """El histórico debe conservarse: el puntaje decide becas."""
    v1 = services.prepoblar_desde_matricula(escenario["exp"])

    v2 = services.verificar_ficha(
        escenario["exp"],
        {"ingresos": {"sueldo_padre": 400}, "convivencia": {"numero_miembros": 4}},
        profesional=escenario["trabajador"],
    )

    v1.refresh_from_db()
    assert v2.version == 2
    assert v2.vigente is True
    assert v1.vigente is False  # ya no vigente...
    assert (
        FichaSocioeconomica.objects.filter(expediente=escenario["exp"]).count() == 2
    )  # pero existe
    assert v2.origen == FichaSocioeconomica.Origen.VERIFICADA


@pytest.mark.django_db
def test_verificacion_arrastra_campos_no_modificados(escenario):
    services.prepoblar_desde_matricula(escenario["exp"])
    v2 = services.verificar_ficha(
        escenario["exp"],
        {"ingresos": {"sueldo": 400}},
        profesional=escenario["trabajador"],
    )
    # vivienda_estudiante no se tocó, pero debe seguir ahí
    assert v2.vivienda_estudiante["canton"] == "Loja"


@pytest.mark.django_db
def test_calcular_totales_ignora_no_numericos(escenario):
    ingresos, egresos = services.calcular_totales(
        {"sueldo": 400, "bono": "50", "observacion": "no aplica"}, {"arriendo": 150}
    )
    assert ingresos == Decimal("450")
    assert egresos == Decimal("150")


@pytest.mark.django_db
def test_puntaje_y_estrato_por_per_capita(escenario):
    """Ingreso per cápita en SBU decide el estrato."""
    services.prepoblar_desde_matricula(escenario["exp"])
    # 400 / 4 = 100 per cápita; 100/470 = 0.21 SBU -> extrema vulnerabilidad
    ficha = services.verificar_ficha(
        escenario["exp"],
        {"ingresos": {"sueldo": 400}, "convivencia": {"numero_miembros": 4}},
        profesional=escenario["trabajador"],
    )
    assert ficha.puntaje == Decimal("0.21")
    assert ficha.estrato == "Extrema vulnerabilidad"


@pytest.mark.django_db
def test_estrato_sin_vulnerabilidad(escenario):
    services.prepoblar_desde_matricula(escenario["exp"])
    # 2000 / 2 = 1000 per cápita; 1000/470 = 2.13 SBU
    ficha = services.verificar_ficha(
        escenario["exp"],
        {"ingresos": {"sueldo": 2000}, "convivencia": {"numero_miembros": 2}},
        profesional=escenario["trabajador"],
    )
    assert ficha.estrato == "Sin vulnerabilidad económica"


@pytest.mark.django_db
def test_miembros_cero_no_divide_por_cero(escenario):
    services.prepoblar_desde_matricula(escenario["exp"])
    ficha = services.verificar_ficha(
        escenario["exp"],
        {"ingresos": {"sueldo": 470}, "convivencia": {"numero_miembros": 0}},
        profesional=escenario["trabajador"],
    )
    assert ficha.puntaje == Decimal("1.00")  # trata 0 como 1


@pytest.mark.django_db
def test_historial_ordenado(escenario):
    services.prepoblar_desde_matricula(escenario["exp"])
    services.verificar_ficha(
        escenario["exp"], {"ingresos": {"s": 100}}, profesional=escenario["trabajador"]
    )
    services.verificar_ficha(
        escenario["exp"], {"ingresos": {"s": 200}}, profesional=escenario["trabajador"]
    )
    historial = list(services.historial_fichas(escenario["exp"]))
    assert [f.version for f in historial] == [3, 2, 1]


@pytest.mark.django_db
def test_visita_domiciliaria(escenario):
    atencion = services.crear_atencion_ts(
        expediente=escenario["exp"], profesional=escenario["trabajador"], motivo="Verificación"
    )
    visita = services.registrar_visita(
        atencion,
        condiciones={"servicios_basicos": True},
        georreferencia={"lat": -4.0, "lng": -79.2},
        observaciones="Vivienda en buen estado",
    )
    assert visita.condiciones_verificadas["servicios_basicos"] is True


@pytest.mark.django_db
def test_visita_futura_rechazada(escenario):
    atencion = services.crear_atencion_ts(
        expediente=escenario["exp"], profesional=escenario["trabajador"]
    )
    with pytest.raises(ValidationError, match="fecha futura"):
        services.registrar_visita(atencion, fecha=timezone.localdate() + timedelta(days=1))


# ==========================================================================
# Una sola ficha vigente: es la que decide el puntaje con el que se da una beca
# ==========================================================================


@pytest.mark.django_db
def test_no_puede_haber_dos_fichas_vigentes_del_mismo_expediente(escenario):
    """
    `ficha_vigente()` hace `.filter(vigente=True).first()` sin orden definido.
    Con dos vigentes devolvería una arbitraria, y de ella salen el puntaje y el
    estrato con los que se resuelve una beca. La base tiene que impedirlo.
    """
    from django.db import IntegrityError, transaction

    exp = escenario["exp"]
    FichaSocioeconomica.objects.create(expediente=exp, version=1, vigente=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        FichaSocioeconomica.objects.create(expediente=exp, version=2, vigente=True)


@pytest.mark.django_db
def test_las_versiones_no_se_repiten_en_un_expediente(escenario):
    """El historial se ordena por versión: repetirla lo vuelve ambiguo."""
    from django.db import IntegrityError, transaction

    exp = escenario["exp"]
    FichaSocioeconomica.objects.create(expediente=exp, version=1, vigente=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        FichaSocioeconomica.objects.create(expediente=exp, version=1, vigente=False)


@pytest.mark.django_db
def test_varias_versiones_no_vigentes_conviven(escenario):
    """El historial completo se conserva: solo la vigencia es única."""
    exp = escenario["exp"]
    FichaSocioeconomica.objects.create(expediente=exp, version=1, vigente=False)
    FichaSocioeconomica.objects.create(expediente=exp, version=2, vigente=False)
    FichaSocioeconomica.objects.create(expediente=exp, version=3, vigente=True)
    assert FichaSocioeconomica.objects.filter(expediente=exp).count() == 3


@pytest.mark.django_db
def test_verificar_ficha_deja_una_sola_vigente(escenario):
    """
    El versionado desmarcaba la anterior DESPUÉS de crear la nueva y sin
    transacción: un fallo entre ambos pasos dejaba dos vigentes.
    """
    exp = escenario["exp"]
    services.prepoblar_desde_matricula(exp)
    ts = escenario["trabajador"]
    services.verificar_ficha(exp, {"ingresos": {"sueldo": 400}}, profesional=ts)
    services.verificar_ficha(exp, {"ingresos": {"sueldo": 500}}, profesional=ts)

    vigentes = FichaSocioeconomica.objects.filter(expediente=exp, vigente=True)
    assert vigentes.count() == 1
    assert vigentes.first().version == 3
    assert FichaSocioeconomica.objects.filter(expediente=exp).count() == 3
