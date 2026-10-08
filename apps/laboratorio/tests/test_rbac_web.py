"""
Control de acceso de las pantallas de Laboratorio.

`bandeja` y `detalle_orden` exigían solo `@login_required`. Un resultado de
laboratorio es contenido clínico: cualquier usuario autenticado leía los de
cualquier paciente cambiando el id de la URL, y por POST registraba, validaba
o publicaba resultados ajenos —publicar además los envía al correo del
paciente—.

Misma regresión que el Sprint 10 corrigió en Medicina y Enfermería.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import CIE10, Seccion, Servicio
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.laboratorio import services
from apps.laboratorio.models import Examen, OrdenLaboratorio
from apps.medicina import services as med_services
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    seccion, _ = Seccion.objects.get_or_create(codigo="salud", defaults={"nombre": "Salud"})
    laboratorio, _ = Servicio.objects.get_or_create(
        codigo="laboratorio-clinico",
        defaults={"nombre": "Laboratorio Clínico", "seccion": seccion},
    )
    tecnico, _ = crear_profesional("tecnico_web", laboratorio, seccion)
    medico, perfil_medico = crear_profesional("medico_lab_web", est["medicina"], est["salud"])
    estudiante = Usuario.objects.create_user(
        username="estudiante_lab", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    for usuario in (tecnico, medico, estudiante):
        usuario.set_password(CLAVE)
        usuario.save()

    exp = crear_expediente(cedula="1104567894")
    CIE10.objects.get_or_create(codigo="J00", defaults={"descripcion": "Resfriado"})
    examen = Examen.objects.create(codigo="LAB-001", nombre="Biometría hemática")
    hc = med_services.crear_atencion_medicina(
        expediente=exp, profesional=perfil_medico, motivo="Fiebre"
    )
    orden = services.crear_orden(hc.atencion, [examen.pk], usuario=medico)
    return {"tecnico": tecnico, "medico": medico, "estudiante": estudiante, "orden": orden}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


@pytest.mark.django_db
def test_la_bandeja_no_se_abre_desde_fuera_del_servicio(escenario):
    for clave in ("estudiante", "medico"):
        assert _cliente(escenario[clave]).get(reverse("laboratorio:bandeja")).status_code == 403


@pytest.mark.django_db
def test_los_resultados_de_un_paciente_no_se_leen_desde_fuera(escenario):
    url = reverse("laboratorio:detalle", args=[escenario["orden"].pk])
    for clave in ("estudiante", "medico"):
        assert _cliente(escenario[clave]).get(url).status_code == 403


@pytest.mark.django_db
def test_nadie_de_fuera_toma_la_muestra_por_post(escenario):
    """El médico tiene perfil profesional, así que el POST llegaba al servicio."""
    url = reverse("laboratorio:detalle", args=[escenario["orden"].pk])
    respuesta = _cliente(escenario["medico"]).post(
        url, {"accion": "tomar_muestra", "tipo_muestra": "sangre"}
    )
    assert respuesta.status_code == 403
    escenario["orden"].refresh_from_db()
    assert escenario["orden"].estado == OrdenLaboratorio.Estado.CREADA


@pytest.mark.django_db
def test_el_tecnico_del_laboratorio_si_entra(escenario):
    cliente = _cliente(escenario["tecnico"])
    assert cliente.get(reverse("laboratorio:bandeja")).status_code == 200
    url = reverse("laboratorio:detalle", args=[escenario["orden"].pk])
    assert cliente.get(url).status_code == 200


@pytest.mark.django_db
def test_un_rango_de_referencia_que_empieza_en_cero_se_ve(escenario):
    """
    `{% if p.parametro.ref_min %}` es falso con 0, así que el rango entero
    desaparecía de la pantalla: bilirrubina directa 0 – 0,3 salía como «—», y
    sin rango el profesional no puede interpretar el resultado.

    Además se imprimía «12,000 – 16,000» por los tres decimales del campo. En
    español eso es doce coma cero, pero de reojo se lee doce mil, y es la
    pantalla donde un valor mal leído tiene consecuencias.
    """
    from decimal import Decimal

    from apps.laboratorio.models import ParametroExamen

    examen = escenario["orden"].examenes.first().examen
    ParametroExamen.objects.create(
        examen=examen,
        nombre="Bilirrubina directa",
        unidad="mg/dL",
        ref_min=Decimal("0.000"),
        ref_max=Decimal("0.300"),
        orden=9,
    )
    contenido = (
        _cliente(escenario["tecnico"])
        .get(reverse("laboratorio:detalle", args=[escenario["orden"].pk]))
        .content.decode()
    )
    assert "Bilirrubina directa" in contenido
    assert "0 – 0,3" in contenido, "el rango que empieza en cero no aparece"
