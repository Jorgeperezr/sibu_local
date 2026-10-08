"""
Dos defectos que reventaban Psicopedagogía en cuanto se usaba con datos reales.

El módulo tenía 417 líneas de código y 128 de pruebas, el peor ratio del
sistema, y sus pruebas trabajaban sobre personas sin datos académicos
cargados. Con esos datos —el caso normal en producción, porque la carga
institucional es lo primero que se hace— pasaba lo siguiente:

1. Abrir una ficha reventaba con `AttributeError`. `_historial_desde_academico`
   leía `d.promedio` y `DatoAcademico` no tiene ese campo. Con la tabla vacía el
   bucle no itera y nadie lo nota; con una sola fila cargada, error 500.

2. Un promedio mal tecleado reventaba con `InvalidOperation`. La validación
   hace `Decimal(str(valor))` para comprobar el rango, y ese constructor lanza
   una excepción de `decimal` que no es `ValidationError`: la vista solo captura
   `ValidationError` y `KeyError`, así que un «8,5» con coma —o cualquier cosa
   que no sea un número— devolvía una página de error en vez de un aviso.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.core.models import PeriodoAcademico
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.psicopedagogia import services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    from apps.core.models import Seccion, Servicio

    est = crear_estructura()
    seccion = Seccion.objects.get(codigo="psicopedagogica")
    servicio, _ = Servicio.objects.get_or_create(
        codigo="psicopedagogia", defaults={"nombre": "Psicopedagogía", "seccion": seccion}
    )
    usuario, perfil = crear_profesional("psp_def", servicio, seccion)
    usuario.set_password(CLAVE)
    usuario.save()
    periodo = PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril–Agosto 2026",
        fecha_inicio="2026-04-01",
        fecha_fin="2026-08-31",
        vigente=True,
    )
    return {"usuario": usuario, "perfil": perfil, "periodo": periodo, "est": est}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------- 1. la ficha con datos cargados


@pytest.mark.django_db
def test_se_abre_una_ficha_de_alguien_con_datos_academicos_cargados(escenario):
    """
    El caso normal en producción: la carga institucional es lo primero que se
    hace. Con la tabla vacía el bucle del historial no itera y el defecto no se
    nota; con una sola fila, revienta.
    """
    from apps.academico.models import DatoAcademico

    expediente = crear_expediente()
    DatoAcademico.objects.create(
        persona=expediente.persona,
        periodo=escenario["periodo"],
        carrera="Medicina",
        facultad="Salud Humana",
        nivel="3",
        ciclo="3",
        estado="Matriculado",
    )

    ficha = services.crear_ficha(
        expediente=expediente, profesional=escenario["perfil"], motivo="Bajo rendimiento"
    )
    assert ficha.historial_academico, "el historial salió vacío pese a haber datos"
    assert "2026-1" in ficha.historial_academico
    assert ficha.historial_academico["2026-1"]["carrera"] == "Medicina"


@pytest.mark.django_db
def test_la_pantalla_tampoco_revienta(escenario):
    from apps.academico.models import DatoAcademico

    expediente = crear_expediente(cedula="1101002002")
    DatoAcademico.objects.create(
        persona=expediente.persona,
        periodo=escenario["periodo"],
        carrera="Computación",
        facultad="Energía",
        nivel="5",
        ciclo="5",
        estado="Matriculado",
    )
    respuesta = _cliente(escenario["usuario"]).post(
        reverse("psicopedagogia:iniciar", args=[expediente.pk]), {"motivo": "Bajo rendimiento"}
    )
    assert respuesta.status_code in (200, 302), respuesta.status_code

    from apps.psicopedagogia.models import FichaPsicopedagogica

    assert FichaPsicopedagogica.objects.filter(atencion__expediente=expediente).exists()


# ------------------------------------------------- 2. un promedio mal escrito


@pytest.mark.django_db
def test_un_promedio_con_coma_se_entiende(escenario):
    """
    «8,5» es como se escribe un decimal en Ecuador, y ahora se lee.

    Esta prueba cambió de sentido a propósito. `Decimal("8,5")` lanzaba
    `InvalidOperation` y salía una página de error; el primer arreglo capturó
    la excepción y pidió punto decimal, y esta prueba fijó ESE comportamiento.
    Pedir punto decimal es rechazar el formato correcto: el arreglo de verdad
    es leer la coma, que es lo que hace ahora `core.numeros`.

    Se guarda lo leído y no lo tecleado: la cadena «8,5» en un campo decimal
    vuelve a romper en el momento de escribir, donde ya no hay a quién avisar.
    """
    from decimal import Decimal

    expediente = crear_expediente(cedula="1103003008")
    ficha = services.crear_ficha(
        expediente=expediente, profesional=escenario["perfil"], motivo="Bajo rendimiento"
    )
    seguimiento = services.registrar_seguimiento(ficha, "2026-1", promedio_antes="8,5")
    seguimiento.refresh_from_db()
    assert seguimiento.promedio_antes == Decimal("8.5")


@pytest.mark.django_db
def test_un_promedio_que_no_es_un_numero_sigue_avisando(escenario):
    """Leer la coma no puede volverse tragarse cualquier cosa."""
    expediente = crear_expediente(cedula="1109009009")
    ficha = services.crear_ficha(
        expediente=expediente, profesional=escenario["perfil"], motivo="Bajo rendimiento"
    )
    with pytest.raises(ValidationError, match="número"):
        services.registrar_seguimiento(ficha, "2026-1", promedio_antes="ocho coma cinco")


@pytest.mark.django_db
def test_la_pantalla_avisa_del_promedio_mal_escrito(escenario):
    expediente = crear_expediente(cedula="1104004005")
    ficha = services.crear_ficha(
        expediente=expediente, profesional=escenario["perfil"], motivo="Bajo rendimiento"
    )
    respuesta = _cliente(escenario["usuario"]).post(
        reverse("psicopedagogia:ficha", args=[ficha.pk]),
        {"accion": "seguimiento", "periodo": "2026-1", "promedio_antes": "ocho"},
    )
    assert respuesta.status_code < 500, "un promedio mal escrito devolvió una página de error"


@pytest.mark.django_db
def test_un_promedio_correcto_sigue_entrando(escenario):
    """La corrección no puede rechazar lo que sí es un número."""
    expediente = crear_expediente(cedula="1105005001")
    ficha = services.crear_ficha(
        expediente=expediente, profesional=escenario["perfil"], motivo="Bajo rendimiento"
    )
    seguimiento = services.registrar_seguimiento(
        ficha, "2026-1", promedio_antes="6.5", promedio_despues="8.0"
    )
    assert seguimiento.promedio_antes is not None
    assert services.impacto(ficha)["mejoro"] is True
