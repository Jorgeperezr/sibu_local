"""
Lo que el portal pinta tiene que existir de verdad.

Django no avisa de un atributo inexistente en una plantilla: lo resuelve a
cadena vacía y sigue. La tarjeta «Mis recetas» pedía `{{ r.codigo }}` y el
modelo tiene `numero`, así que el paciente veía una fila con la etiqueta
«Emitida» y nada más. Ninguna prueba lo vio: todas miraban el contexto o el
código de estado, y el 200 era correcto.

Estas comprueban lo contrario que las demás del portal —que no se filtre lo
ajeno— : que lo propio SÍ aparezca.
"""

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.portal.models import VinculacionPortal
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def paciente(db):
    from datetime import timedelta

    from apps.expediente.tests.factories import (
        crear_atencion,
        crear_estructura,
        crear_expediente,
        crear_profesional,
    )
    from apps.farmacia import services as farmacia
    from apps.farmacia.models import Medicamento

    est = crear_estructura()
    _, perfil = crear_profesional("med_portal", est["medicina"], est["salud"])
    expediente = crear_expediente()
    atencion = crear_atencion(expediente, est["medicina"], perfil)

    medicamento = Medicamento.objects.create(
        codigo="MED-P1",
        dci="Paracetamol",
        concentracion="500 mg",
        forma_farmaceutica="tableta",
        unidad_medida="tableta",
    )
    receta = farmacia.emitir_receta(
        atencion,
        [{"medicamento_id": medicamento.pk, "cantidad_prescrita": 10, "dosis": "1 tableta"}],
    )

    usuario = Usuario.objects.create_user(
        username="pac_portal", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    VinculacionPortal.objects.create(
        usuario=usuario,
        expediente=expediente,
        verificado=True,
        correo_destino="p@unl.edu.ec",
        token_hash="x",
        token_expira_en=timezone.now() + timedelta(hours=1),
    )
    cliente = Client()
    assert cliente.login(username="pac_portal", password=CLAVE)
    return {"cliente": cliente, "receta": receta, "medicamento": medicamento}


@pytest.mark.django_db
def test_la_receta_se_ve_con_su_numero(paciente):
    """Una fila de receta sin número no le dice nada a quien va a la farmacia."""
    contenido = paciente["cliente"].get(reverse("portal:inicio")).content.decode()
    assert paciente["receta"].numero in contenido, "la receta salió sin número"


@pytest.mark.django_db
def test_la_receta_dice_qué_medicamento_es(paciente):
    """
    `mis_recetas` ya venía haciendo `prefetch_related("detalles__medicamento")`:
    la intención de mostrarlos estaba, y la plantilla no los pintaba.
    """
    contenido = paciente["cliente"].get(reverse("portal:inicio")).content.decode()
    assert paciente["medicamento"].dci in contenido, "no se ve qué le recetaron"


@pytest.mark.django_db
def test_ninguna_tarjeta_del_panel_queda_en_blanco(paciente):
    """
    La guarda general: si alguien renombra un campo, la plantilla sigue
    devolviendo 200 y pintando huecos. Esto compara lo que la plantilla pide de
    cada modelo contra los campos que el modelo tiene.
    """
    import pathlib
    import re

    from django.apps import apps as registro

    plantilla = pathlib.Path("templates/portal/panel.html").read_text()
    # (alias del bucle, modelo) tal como aparecen en el panel.
    # Los talleres salieron del panel: los ve el personal del servicio que los
    # organiza, no quien asiste.
    ALIAS = [("b", "becas.BecaBeneficiario")]
    faltantes = []
    for alias, etiqueta in ALIAS:
        modelo = registro.get_model(*etiqueta.split("."))
        campos = {f.name for f in modelo._meta.get_fields()}
        for usado in set(re.findall(r"\{\{ *" + alias + r"\.([a-z_]+)", plantilla)):
            if usado not in campos and not usado.startswith("get_") and usado != "pk":
                faltantes.append(f"{etiqueta}.{usado}")
    assert faltantes == [], f"la plantilla pide campos que no existen: {faltantes}"
