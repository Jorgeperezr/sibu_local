"""Pruebas de los validadores (cédula ecuatoriana, correo, conversiones)."""

from apps.academico import validators
from apps.academico.tests.factories import generar_cedula


def test_cedula_valida():
    assert validators.validar_cedula_ecuatoriana(generar_cedula())


def test_cedula_invalida_por_verificador():
    valida = generar_cedula()
    ultimo = (int(valida[-1]) + 1) % 10
    assert not validators.validar_cedula_ecuatoriana(valida[:-1] + str(ultimo))


def test_cedula_provincia_invalida():
    assert not validators.validar_cedula_ecuatoriana("9999999999")


def test_normalizar_cedula_rellena_cero():
    assert validators.normalizar_cedula("123456789") == "0123456789"


def test_correo_institucional():
    assert validators.validar_correo_institucional("a.b@unl.edu.ec", "unl.edu.ec")
    assert not validators.validar_correo_institucional("a.b@gmail.com", "unl.edu.ec")


def test_a_decimal_y_fecha():
    assert validators.a_decimal("1200.50") == validators.Decimal("1200.50")
    assert validators.a_decimal("no-num") == validators.Decimal("0")
    assert validators.a_fecha("15/03/2000").year == 2000
