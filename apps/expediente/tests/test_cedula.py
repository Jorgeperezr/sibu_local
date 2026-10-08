"""
La cédula es la clave de vinculación del expediente único.

`academico`, `talleres` y `portal` ya validaban en su propio servicio, pero el
modelo aceptaba cualquier cadena: el admin de Django, el shell o una migración
de datos colaban una cédula imposible y creaban una persona que ya no se puede
cruzar con nada.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.expediente.models import Persona


@pytest.mark.django_db
def test_una_cedula_que_no_pasa_modulo_10_se_rechaza():
    with pytest.raises(ValidationError) as exc:
        Persona.objects.create(
            cedula="1104567890",  # dígito verificador incorrecto
            nombres="Test",
            apellidos="Paciente",
            tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
        )
    assert "cedula" in exc.value.message_dict


@pytest.mark.django_db
def test_una_cedula_valida_se_acepta():
    p = Persona.objects.create(
        cedula="1104567894",
        nombres="Test",
        apellidos="Paciente",
        tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
    )
    assert p.pk is not None


@pytest.mark.django_db
def test_la_cedula_se_normaliza_antes_de_guardar():
    """Excel se come el cero inicial: 0900000001 llega como 900000001."""
    p = Persona.objects.create(
        cedula="900000001",
        nombres="Test",
        apellidos="Cero",
        tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
    )
    assert p.cedula == "0900000001"


@pytest.mark.django_db
def test_un_pasaporte_no_pasa_por_el_modulo_10():
    """Un externo con pasaporte es un caso legítimo: no es cédula ecuatoriana."""
    p = Persona.objects.create(
        cedula="X1234567",
        tipo_documento="pasaporte",
        nombres="Jane",
        apellidos="Doe",
        tipo_vinculo=Persona.TipoVinculo.EXTERNO,
    )
    assert p.pk is not None
