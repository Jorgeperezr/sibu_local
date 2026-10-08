"""
El botón de exportar historial: uno por bandeja, y en la cabecera.

Está en las ocho bandejas no confidenciales por medio de un fragmento común, y
dos plantillas lo habían colocado en otro sitio. Los dos fallos responden 200 y
solo se ven mirando:

- **Becas** lo metió DENTRO de la tarjeta de conteo y dentro del `{% for %}` que
  la pinta. Con un tipo de beca parecía un botón descolocado; con tres habría
  salido tres veces, el mismo botón repetido junto a cada cifra.
- **Laboratorio** lo dejó después de la tabla y dentro del `table-responsive`,
  así que colgaba del marco como si fuera una fila más y en una pantalla
  estrecha se va con el desplazamiento horizontal.

Se comprueba la cantidad —que es lo que atrapa la repetición— y la posición
relativa a la tabla, que es lo que atrapa el descuelgue.
"""

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.core.models import Servicio
from apps.usuarios.models import PerfilProfesional, Rol, Usuario

CLAVE = "clave-larga-12345"

# Las ocho bandejas que ofrecen exportación, con su ruta.
BANDEJAS = [
    ("medicina", "/medicina/"),
    ("enfermeria", "/enfermeria/"),
    ("odontologia", "/odontologia/"),
    ("laboratorio-clinico", "/laboratorio/"),
    ("farmacia", "/farmacia/"),
    ("psicopedagogia", "/psicopedagogia/"),
    ("trabajo-social", "/trabajo-social/"),
    ("becas-y-ayudas-economicas", "/becas/"),
]


@pytest.fixture
def profesional(db):
    """Alguien con los nueve servicios: ve todas las bandejas."""
    call_command("seed_inicial", verbosity=0)
    usuario = Usuario.objects.create_user(
        username="exporta", password=CLAVE, rol_principal=Rol.PROFESIONAL
    )
    perfil = PerfilProfesional.objects.create(usuario=usuario)
    perfil.servicios.set(Servicio.objects.all())
    cliente = Client()
    assert cliente.login(username="exporta", password=CLAVE)
    return cliente


@pytest.mark.parametrize(("codigo", "ruta"), BANDEJAS)
@pytest.mark.django_db
def test_el_boton_de_exportar_sale_una_sola_vez(codigo, ruta, profesional):
    contenido = profesional.get(ruta).content.decode()
    enlace = f"{reverse('reportes:exportar_hoja')}?servicio={codigo}"

    assert contenido.count(enlace) == 1, (
        f"{ruta} pinta el botón de exportar {contenido.count(enlace)} veces. "
        "Si está dentro de un bucle, sale uno por cada fila."
    )


@pytest.mark.parametrize(("codigo", "ruta"), BANDEJAS)
@pytest.mark.django_db
def test_el_boton_de_exportar_va_en_la_cabecera(codigo, ruta, profesional):
    """
    Antes de la tabla. Detrás queda colgando del marco como una fila más, y
    dentro de un `table-responsive` se va con el desplazamiento horizontal.
    """
    contenido = profesional.get(ruta).content.decode()
    boton = contenido.find(f"{reverse('reportes:exportar_hoja')}?servicio={codigo}")
    tabla = contenido.find("<table")

    assert boton != -1, f"{ruta} no pinta el botón de exportar"
    if tabla != -1:
        assert boton < tabla, f"{ruta} pinta el botón de exportar después de la tabla"


@pytest.mark.django_db
def test_psicologia_no_ofrece_exportar(profesional):
    """
    El sello: su historial no sale de la Unidad, y ofrecer un botón que va a
    decir que no se puede es peor que no ofrecerlo.
    """
    contenido = profesional.get("/psicologia/").content.decode()

    # El enlace CON servicio, no el texto: «Exportar historial» también nombra
    # el módulo del menú lateral, que es otra pantalla y sí le corresponde.
    assert "?servicio=psicologia" not in contenido
