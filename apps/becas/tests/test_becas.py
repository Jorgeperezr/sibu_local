"""
Becas — fase 1: seguimiento de beneficiarios.

SIBU no adjudica ni desembolsa. Registra, verifica matrícula e informa. Las
reglas que importan son las que protegen a la persona becada: no se le quita la
beca sola ni sin causal escrita.
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.becas import services
from apps.becas.models import BecaBeneficiario, SeguimientoBeca, TipoBeca
from apps.core.models import PeriodoAcademico
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)


@pytest.fixture
def escenario(db):
    from apps.core.models import Seccion, Servicio

    crear_estructura()
    seccion, _ = Seccion.objects.get_or_create(codigo="becas", defaults={"nombre": "Becas"})
    servicio, _ = Servicio.objects.get_or_create(
        codigo="becas-y-ayudas-economicas",
        defaults={"nombre": "Becas y ayudas económicas", "seccion": seccion},
    )
    u, prof = crear_profesional("trabajadora", servicio, seccion)
    exp = crear_expediente(cedula="1104567894")

    p1, _ = PeriodoAcademico.objects.get_or_create(
        codigo="2026-1",
        defaults={
            "nombre": "2026-1",
            "fecha_inicio": date(2026, 3, 1),
            "fecha_fin": date(2026, 7, 31),
            "vigente": True,
        },
    )
    p2, _ = PeriodoAcademico.objects.get_or_create(
        codigo="2026-2",
        defaults={
            "nombre": "2026-2",
            "fecha_inicio": date(2026, 9, 1),
            "fecha_fin": date(2027, 1, 31),
            "vigente": False,
        },
    )
    tipo, _ = TipoBeca.objects.get_or_create(
        codigo="socioeconomica", defaults={"nombre": "Socioeconómica"}
    )
    tipo2, _ = TipoBeca.objects.get_or_create(codigo="academica", defaults={"nombre": "Académica"})
    return {
        "u": u,
        "prof": prof,
        "exp": exp,
        "p1": p1,
        "p2": p2,
        "tipo": tipo,
        "tipo2": tipo2,
        "servicio": servicio,
    }


def _registrar(e, **extra):
    datos = {
        "expediente": e["exp"],
        "tipo_beca": e["tipo"],
        "periodo_desde": e["p1"],
        "profesional": e["prof"],
        "usuario": e["u"],
        "resolucion": "RES-001",
    }
    datos.update(extra)
    return services.registrar_beneficiario(**datos)


# --------------------------------------------------------------------------
# Registro
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_registrar_beneficiario(escenario):
    b = _registrar(escenario)
    assert b.estado == BecaBeneficiario.Estado.REGISTRADO
    assert b.origen == BecaBeneficiario.Origen.MANUAL


@pytest.mark.django_db
def test_el_registro_queda_auditado(escenario):
    from apps.auditoria.models import LogAuditoria

    b = _registrar(escenario)
    log = LogAuditoria.objects.filter(modulo="becas", entidad_id=str(b.pk)).first()
    assert log is not None
    assert log.expediente_id == escenario["exp"].pk


@pytest.mark.django_db
def test_no_se_duplica_una_beca_activa(escenario):
    """Un duplicado se leería como dos adjudicaciones y falsearía los conteos."""
    _registrar(escenario)
    with pytest.raises(ValidationError, match="ya tiene una beca activa"):
        _registrar(escenario)


@pytest.mark.django_db
def test_si_se_termina_la_anterior_se_puede_registrar_otra(escenario):
    b = _registrar(escenario)
    services.cambiar_estado(b, BecaBeneficiario.Estado.TERMINADO, causal="Se graduó")
    otra = _registrar(escenario)
    assert otra.pk != b.pk


@pytest.mark.django_db
def test_otro_tipo_de_beca_si_convive(escenario):
    _registrar(escenario)
    otra = _registrar(escenario, tipo_beca=escenario["tipo2"])
    assert otra.pk


@pytest.mark.django_db
def test_periodo_final_anterior_al_inicial_se_rechaza(escenario):
    escenario["p2"].fecha_inicio = date(2025, 1, 1)
    escenario["p2"].save()
    with pytest.raises(ValidationError, match="no puede ser anterior"):
        _registrar(escenario, periodo_hasta=escenario["p2"])


# --------------------------------------------------------------------------
# Verificación de matrícula
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_verificar_matricula_no_suspende_la_beca(escenario):
    """
    La regla que más importa del módulo.

    Una beca es el sustento de alguien. Quitarla es una decisión de Trabajo
    Social, no el efecto secundario de una consulta automática.
    """
    b = _registrar(escenario)
    seg = services.verificar_matricula(b, escenario["p1"], escenario["prof"])
    b.refresh_from_db()
    assert seg.tipo == SeguimientoBeca.Tipo.VERIFICACION
    assert b.estado == BecaBeneficiario.Estado.REGISTRADO, "La verificación suspendió la beca sola"


@pytest.mark.django_db
def test_sin_datos_academicos_no_se_afirma_que_no_esta_matriculado(escenario):
    """
    Ausencia de dato no es prueba de ausencia de matrícula.

    Puede faltar la carga del periodo. Marcar `False` aquí llevaría a suspender
    becas por un archivo que nadie subió.
    """
    b = _registrar(escenario)
    seg = services.verificar_matricula(b, escenario["p1"], escenario["prof"])
    assert seg.matricula_vigente is None
    assert "No es prueba" in seg.detalle


@pytest.mark.django_db
def test_con_matricula_vigente_se_marca_true(escenario):
    from apps.academico.models import DatoAcademico

    DatoAcademico.objects.create(
        persona=escenario["exp"].persona,
        periodo=escenario["p1"],
        carrera="Sistemas",
        estado="Matriculado",
    )
    b = _registrar(escenario)
    seg = services.verificar_matricula(b, escenario["p1"], escenario["prof"])
    assert seg.matricula_vigente is True
    assert "Sistemas" in seg.detalle


@pytest.mark.django_db
def test_sin_matricula_vigente_se_marca_false_pero_no_suspende(escenario):
    from apps.academico.models import DatoAcademico

    DatoAcademico.objects.create(
        persona=escenario["exp"].persona,
        periodo=escenario["p1"],
        carrera="Sistemas",
        estado="Retirado",
    )
    b = _registrar(escenario)
    seg = services.verificar_matricula(b, escenario["p1"], escenario["prof"])
    assert seg.matricula_vigente is False
    b.refresh_from_db()
    assert b.estado != BecaBeneficiario.Estado.SUSPENDIDO


# --------------------------------------------------------------------------
# Estados
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_suspender_sin_causal_se_rechaza(escenario):
    """Sin causal escrita, un reclamo posterior es indefendible."""
    b = _registrar(escenario)
    with pytest.raises(ValidationError, match="causal"):
        services.cambiar_estado(b, BecaBeneficiario.Estado.SUSPENDIDO, causal="  ")


@pytest.mark.django_db
def test_suspender_con_causal_funciona_y_se_audita(escenario):
    from apps.auditoria.models import LogAuditoria

    b = _registrar(escenario)
    services.cambiar_estado(
        b, BecaBeneficiario.Estado.SUSPENDIDO, causal="Perdió la gratuidad", usuario=escenario["u"]
    )
    b.refresh_from_db()
    assert b.estado == BecaBeneficiario.Estado.SUSPENDIDO
    log = LogAuditoria.objects.filter(detalle__estado_nuevo="suspendido").first()
    assert log.detalle["causal"] == "Perdió la gratuidad"


@pytest.mark.django_db
def test_una_beca_terminada_no_revive(escenario):
    b = _registrar(escenario)
    services.cambiar_estado(b, BecaBeneficiario.Estado.TERMINADO, causal="Culminó")
    with pytest.raises(ValidationError, match="terminada"):
        services.cambiar_estado(b, BecaBeneficiario.Estado.EN_SEGUIMIENTO, causal="x")


@pytest.mark.django_db
def test_un_seguimiento_pasa_la_beca_a_en_seguimiento(escenario):
    b = _registrar(escenario)
    services.registrar_seguimiento(
        b,
        periodo=escenario["p1"],
        tipo=SeguimientoBeca.Tipo.ENTREVISTA,
        detalle="Primera entrevista",
        profesional=escenario["prof"],
    )
    b.refresh_from_db()
    assert b.estado == BecaBeneficiario.Estado.EN_SEGUIMIENTO


@pytest.mark.django_db
def test_seguimiento_sin_detalle_se_rechaza(escenario):
    b = _registrar(escenario)
    with pytest.raises(ValidationError, match="detalle"):
        services.registrar_seguimiento(
            b,
            periodo=escenario["p1"],
            tipo=SeguimientoBeca.Tipo.NOVEDAD,
            detalle="   ",
            profesional=escenario["prof"],
        )


# --------------------------------------------------------------------------
# Datos bancarios: bloqueados en fase 1
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_se_guardan_datos_bancarios(escenario):
    """
    Escribir texto plano en un campo llamado "cifrados" es peor que no tener el
    campo: quien lea el esquema asumirá una protección inexistente.
    """
    b = _registrar(escenario)
    with pytest.raises(ValidationError, match="no almacena datos bancarios"):
        services.guardar_datos_bancarios(b, {"cuenta": "1234567890", "banco": "Loja"})
    b.refresh_from_db()
    assert b.datos_bancarios_cifrados == {}


@pytest.mark.django_db
def test_la_api_no_expone_el_campo_bancario(escenario):
    from apps.becas.serializers import BecaBeneficiarioSerializer

    campos = set(BecaBeneficiarioSerializer().get_fields())
    assert "datos_bancarios_cifrados" not in campos


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_vigentes_excluye_terminadas_y_suspendidas(escenario):
    b1 = _registrar(escenario)
    b2 = _registrar(escenario, tipo_beca=escenario["tipo2"])
    services.cambiar_estado(b2, BecaBeneficiario.Estado.SUSPENDIDO, causal="x")
    vigentes = services.beneficiarios_vigentes(escenario["p1"])
    assert list(vigentes) == [b1]


@pytest.mark.django_db
def test_resumen_por_tipo(escenario):
    _registrar(escenario)
    _registrar(escenario, tipo_beca=escenario["tipo2"])
    resumen = services.resumen_por_tipo(escenario["p1"])
    assert {r["tipo"] for r in resumen} == {"Socioeconómica", "Académica"}
    assert all(r["total"] == 1 for r in resumen)


@pytest.mark.django_db
def test_expirar_vencidas_cierra_por_plazo_no_por_sancion(escenario):
    """El cierre por vencimiento no es un castigo: no exige causal, pero la deja escrita."""
    pasado, _ = PeriodoAcademico.objects.get_or_create(
        codigo="2025-1",
        defaults={
            "nombre": "2025-1",
            "fecha_inicio": date(2025, 3, 1),
            "fecha_fin": date(2025, 7, 31),
            "vigente": False,
        },
    )
    b = _registrar(escenario, periodo_desde=pasado, periodo_hasta=pasado)
    assert services.expirar_vencidas(escenario["p1"]) == 1
    b.refresh_from_db()
    assert b.estado == BecaBeneficiario.Estado.TERMINADO
    assert "finalizó" in b.causal


@pytest.mark.django_db
def test_expirar_no_toca_las_becas_sin_fecha_de_fin(escenario):
    b = _registrar(escenario, periodo_hasta=None)
    services.expirar_vencidas(escenario["p1"])
    b.refresh_from_db()
    assert b.estado == BecaBeneficiario.Estado.REGISTRADO
