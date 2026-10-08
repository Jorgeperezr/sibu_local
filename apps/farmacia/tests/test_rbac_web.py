"""
Control de acceso de las pantallas de Farmacia.

`mostrador`, `despachar` e `inventario` exigían solo `@login_required`.
Cualquier usuario autenticado —un estudiante con rol USUARIO_FINAL incluido—
veía la cola de recetas con el nombre y el diagnóstico de cada paciente, y por
POST podía despachar medicación o anular una receta ajena.

Es la misma regresión que el Sprint 10 corrigió en Medicina y Enfermería; en
Farmacia quedó sin corregir y ninguna prueba web la cubría.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import CIE10, Seccion, Servicio
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.farmacia import services
from apps.farmacia.models import Medicamento, Receta
from apps.medicina import services as med_services
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    seccion, _ = Seccion.objects.get_or_create(codigo="salud", defaults={"nombre": "Salud"})
    farmacia, _ = Servicio.objects.get_or_create(
        codigo="farmacia", defaults={"nombre": "Farmacia", "seccion": seccion}
    )
    quimico, perfil_quimico = crear_profesional("quimico_web", farmacia, seccion)
    medico, perfil_medico = crear_profesional("medico_web", est["medicina"], est["salud"])
    for usuario in (quimico, medico):
        usuario.set_password(CLAVE)
        usuario.save()

    exp = crear_expediente(cedula="1104567894")
    CIE10.objects.get_or_create(codigo="J00", defaults={"descripcion": "Resfriado"})
    medicamento = Medicamento.objects.create(
        codigo="MED-001",
        dci="Paracetamol",
        concentracion="500 mg",
        unidad_medida="tableta",
        stock_minimo=50,
    )
    services.ingresar_lote(
        medicamento,
        "L-001",
        100,
        timezone.localdate() + timedelta(days=365),
        usuario=perfil_quimico,
    )
    hc = med_services.crear_atencion_medicina(
        expediente=exp, profesional=perfil_medico, motivo="Fiebre"
    )
    receta = services.emitir_receta(
        hc.atencion,
        [
            {
                "medicamento_id": medicamento.pk,
                "cantidad_prescrita": 9,
                "dosis": "1 tableta",
                "via": "oral",
                "frecuencia": "cada 8h",
            }
        ],
        usuario=medico,
    )
    return {
        "farmacia": farmacia,
        "quimico": quimico,
        "medico": medico,
        "medicamento": medicamento,
        "receta": receta,
    }


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


@pytest.fixture
def estudiante(db):
    usuario = Usuario.objects.create_user(
        username="estudiante_web", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    return usuario


@pytest.mark.parametrize("vista", ["farmacia:mostrador", "farmacia:inventario"])
@pytest.mark.django_db
def test_un_estudiante_no_abre_las_pantallas_de_farmacia(escenario, estudiante, vista):
    assert _cliente(estudiante).get(reverse(vista)).status_code == 403


@pytest.mark.django_db
def test_un_profesional_de_otro_servicio_tampoco(escenario):
    """El médico prescribe, pero no despacha: el inventario no es suyo."""
    assert _cliente(escenario["medico"]).get(reverse("farmacia:mostrador")).status_code == 403


@pytest.mark.django_db
def test_la_ficha_de_una_receta_ajena_no_se_abre(escenario, estudiante):
    url = reverse("farmacia:despachar", args=[escenario["receta"].pk])
    assert _cliente(estudiante).get(url).status_code == 403


@pytest.mark.django_db
def test_nadie_de_fuera_anula_una_receta_por_post(escenario, estudiante):
    """
    El médico es el caso serio: tiene perfil profesional, así que la vista no
    lo frenaba por ahí y llegaba a `anular_receta`. El estudiante se salvaba de
    milagro —por no tener perfil—, no por control de acceso.
    """
    url = reverse("farmacia:despachar", args=[escenario["receta"].pk])
    for usuario in (escenario["medico"], estudiante):
        respuesta = _cliente(usuario).post(url, {"accion": "anular", "motivo": "porque sí"})
        assert respuesta.status_code == 403
    escenario["receta"].refresh_from_db()
    assert escenario["receta"].estado != Receta.Estado.ANULADA


@pytest.mark.django_db
def test_el_farmaceutico_si_entra(escenario):
    cliente = _cliente(escenario["quimico"])
    assert cliente.get(reverse("farmacia:mostrador")).status_code == 200
    assert cliente.get(reverse("farmacia:inventario")).status_code == 200
    assert (
        cliente.get(reverse("farmacia:despachar", args=[escenario["receta"].pk])).status_code == 200
    )
