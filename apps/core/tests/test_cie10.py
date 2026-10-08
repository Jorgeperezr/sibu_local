"""
Catálogo CIE-10 y su reparto por servicio.

Antes de este comando la tabla CIE10 estaba prácticamente vacía —solo lo que
cada prueba creaba con `get_or_create`—: en producción, escribir un código
CIE-10 en la consulta médica no encontraba nada.
"""

import pytest

from apps.core.management.commands.cargar_cie10 import CATALOGO
from apps.core.models import CIE10
from apps.core.selectors import diagnosticos_por_servicio


@pytest.mark.django_db
def test_el_comando_carga_el_catalogo():
    from django.core.management import call_command

    call_command("cargar_cie10")
    assert CIE10.objects.count() == len(CATALOGO)


@pytest.mark.django_db
def test_el_comando_es_idempotente():
    from django.core.management import call_command

    call_command("cargar_cie10")
    call_command("cargar_cie10")
    assert CIE10.objects.count() == len(CATALOGO)


@pytest.mark.django_db
def test_no_hay_codigos_duplicados_en_el_catalogo():
    codigos = [codigo for codigo, _, _ in CATALOGO]
    assert len(codigos) == len(set(codigos))


@pytest.mark.django_db
def test_odontologia_no_ve_codigos_de_salud_mental():
    from django.core.management import call_command

    call_command("cargar_cie10")
    codigos = set(diagnosticos_por_servicio("odontologia").values_list("codigo", flat=True))
    assert "K02" in codigos  # caries
    assert "F32" not in codigos  # episodio depresivo


@pytest.mark.django_db
def test_medicina_no_ve_lo_propio_de_odontologia_ni_psicopedagogia():
    from django.core.management import call_command

    call_command("cargar_cie10")
    codigos = set(diagnosticos_por_servicio("medicina").values_list("codigo", flat=True))
    assert "J00" in codigos  # resfriado común: sí es de medicina general
    assert "K02" not in codigos  # caries: es de odontología
    assert "F81" not in codigos  # trastorno del aprendizaje: es de psicopedagogía


@pytest.mark.django_db
def test_psicologia_ve_salud_mental_y_lo_del_desarrollo():
    from django.core.management import call_command

    call_command("cargar_cie10")
    codigos = set(diagnosticos_por_servicio("psicologia").values_list("codigo", flat=True))
    assert "F32" in codigos
    assert "F90" in codigos  # trastorno hipercinético, también psicopedagógico


@pytest.mark.django_db
def test_un_servicio_sin_diagnostico_no_ve_nada():
    from django.core.management import call_command

    call_command("cargar_cie10")
    assert not diagnosticos_por_servicio("farmacia").exists()
