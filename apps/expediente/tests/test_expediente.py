"""Pruebas de resolución de expediente y break-the-glass."""

import pytest

from apps.auditoria.models import LogAuditoria
from apps.expediente.services import resolver_por_cedula
from apps.expediente.tests.factories import crear_expediente
from apps.usuarios.models import Rol, Usuario
from apps.usuarios.services import registrar_break_glass


@pytest.mark.django_db
def test_resolver_por_cedula_existente():
    exp = crear_expediente(cedula="1104567894")
    resultado = resolver_por_cedula("1104567894")
    assert resultado["persona"].cedula == "1104567894"
    assert resultado["expediente"].id == exp.id


@pytest.mark.django_db
def test_resolver_cedula_inexistente_devuelve_none():
    assert resolver_por_cedula("0000000000") is None


@pytest.mark.django_db
def test_break_glass_queda_auditado():
    exp = crear_expediente()
    user = Usuario.objects.create_user(username="u", password="x", rol_principal=Rol.PROFESIONAL)
    registrar_break_glass(user, exp.id, "Paciente inconsciente en emergencia")
    log = LogAuditoria.objects.filter(accion=LogAuditoria.Accion.BREAK_GLASS).first()
    assert log is not None
    assert log.expediente_id == exp.id
    assert "motivo" in log.detalle
