"""Prueba de humo: la estructura del seed se crea correctamente."""

import pytest
from django.core.management import call_command

from apps.core.models import Seccion, Servicio


@pytest.mark.django_db
def test_seed_inicial_crea_estructura():
    call_command("seed_inicial")
    assert Seccion.objects.count() == 4
    assert Servicio.objects.count() == 9
    # Los servicios psicopedagógicos y de trabajo social permiten talleres
    assert Servicio.objects.filter(permite_talleres=True).count() == 3
