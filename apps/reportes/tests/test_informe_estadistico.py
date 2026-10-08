"""
Informe estadístico de un servicio.

Distinto del tablero de la Dirección: aquí no hay K_MÍNIMO porque el
profesional que lo genera ya ve el contenido clínico completo de esas
atenciones, una por una. Lo que se prueba es que las ocho columnas pedidas
cuenten lo correcto con su porcentaje sobre el total de atenciones, que cada
profesional vea solo lo suyo, y que el informe separe explícitamente
atenciones de personas atendidas —no son la misma cifra: una persona
atendida tres veces en el rango pesa tres atenciones y es una sola persona—.

Embarazo, lactancia, enfermedad catastrófica y necesidad educativa especial no
tenían dónde vivir en el sistema antes de hoy: se resuelven con los tipos de
`AlertaClinica` añadidos en el mismo commit.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.expediente.models import AlertaClinica, Atencion
from apps.expediente.services import registrar_alerta
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.reportes import services
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("medico_informe", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()

    exp1 = crear_expediente(cedula="1104567894")
    exp1.persona.sexo = "mujer"
    exp1.persona.genero = "femenino"
    exp1.persona.identidad_orientacion_sexual = "heterosexual"
    exp1.persona.save()
    registrar_alerta(exp1, AlertaClinica.Tipo.GESTACION, "Gestación de 20 semanas")

    exp2 = crear_expediente(cedula="1712345675")
    exp2.persona.sexo = "hombre"
    exp2.persona.save()
    exp2.discapacidad_tipo = "física"
    exp2.discapacidad_porcentaje = 30
    exp2.save()

    for exp in (exp1, exp1, exp2):  # exp1 se atiende dos veces, exp2 una.
        Atencion.objects.create(
            expediente=exp,
            servicio=est["medicina"],
            profesional=perfil_medico,
            fecha_hora=timezone.now(),
        )
    return {"est": est, "medico": medico, "exp1": exp1, "exp2": exp2}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_cuenta_por_atencion_no_por_paciente(escenario):
    datos = services.informe_estadistico(escenario["est"]["medicina"])
    assert datos["total_atenciones"] == 3


@pytest.mark.django_db
def test_sexo_genero_e_identidad_orientacion_sexual_se_desglosan(escenario):
    """
    Las etiquetas van agrupadas, no tal como se tecleó cada una.

    Esta prueba fijaba «mujer» y «femenino» en minúscula, que era lo guardado.
    Con cuatro bases institucionales el mismo valor llega escrito de cuatro
    maneras —«F», «f», «Femenino», «Mujer»— y el informe salía con cuatro filas
    para dos grupos; se cuenta por la forma agrupada. Lo declarado se conserva
    igual en el expediente: agrupa el informe, no la base.
    """
    datos = services.informe_estadistico(escenario["est"]["medicina"])
    por_sexo = {f["etiqueta"]: f["total"] for f in datos["sexo"]}
    assert por_sexo == {"Mujer": 2, "Hombre": 1}
    por_genero = {f["etiqueta"]: f["total"] for f in datos["genero"]}
    assert por_genero == {"Femenino": 2, services.SIN_DATO: 1}
    por_identidad = {f["etiqueta"]: f["total"] for f in datos["identidad_orientacion_sexual"]}
    assert por_identidad == {"Heterosexual": 2, services.SIN_DATO: 1}


@pytest.mark.django_db
def test_discapacidad_es_si_o_no(escenario):
    datos = services.informe_estadistico(escenario["est"]["medicina"])
    por_discapacidad = {f["etiqueta"]: f["total"] for f in datos["discapacidad"]}
    assert por_discapacidad == {"Sin discapacidad": 2, "Con discapacidad": 1}


@pytest.mark.django_db
def test_embarazo_cuenta_las_atenciones_con_la_alerta_activa(escenario):
    datos = services.informe_estadistico(escenario["est"]["medicina"])
    assert datos["embarazo"] == {"total": 2, "porcentaje": 66.7}  # 2 de 3 atenciones
    assert datos["lactancia"] == {"total": 0, "porcentaje": 0.0}
    assert datos["enfermedad_catastrofica"] == {"total": 0, "porcentaje": 0.0}
    assert datos["necesidad_educativa_especial"] == {"total": 0, "porcentaje": 0.0}


@pytest.mark.django_db
def test_una_alerta_desactivada_no_cuenta(escenario):
    from apps.expediente.services import desactivar_alerta

    alerta = AlertaClinica.objects.get(expediente=escenario["exp1"])
    desactivar_alerta(alerta)
    datos = services.informe_estadistico(escenario["est"]["medicina"])
    assert datos["embarazo"]["total"] == 0


@pytest.mark.django_db
def test_el_porcentaje_es_sobre_atenciones_no_sobre_personas(escenario):
    """
    El ejemplo pedido: si hay 3 atenciones y 2 corresponden a una categoría,
    el porcentaje es 2/3 —sobre atenciones—, no 2/2 personas ni ninguna otra
    cuenta. exp1 se atendió dos veces y es "mujer": 2 de 3 atenciones, 66.7 %.
    """
    datos = services.informe_estadistico(escenario["est"]["medicina"])
    fila_mujer = next(f for f in datos["sexo"] if f["etiqueta"] == "Mujer")
    assert fila_mujer == {"etiqueta": "Mujer", "total": 2, "porcentaje": 66.7}


@pytest.mark.django_db
def test_sin_atenciones_el_porcentaje_no_revienta(escenario):
    """División por cero: un servicio sin atenciones no debe fallar, debe dar 0 %."""
    datos = services.informe_estadistico(escenario["est"]["psicologia"])
    assert datos["embarazo"] == {"total": 0, "porcentaje": 0.0}


@pytest.mark.django_db
def test_separa_atenciones_de_personas_atendidas(escenario):
    """
    exp1 se atendió dos veces, exp2 una: 3 atenciones, pero 2 personas
    distintas. Es justo la distinción que el informe no puede difuminar.
    """
    datos = services.informe_estadistico(escenario["est"]["medicina"])
    assert datos["total_atenciones"] == 3
    assert datos["total_pacientes"] == 2


@pytest.mark.django_db
def test_filtra_por_fecha(escenario):
    Atencion.objects.filter(expediente=escenario["exp2"]).update(
        fecha_hora=timezone.now() - timedelta(days=30)
    )
    datos = services.informe_estadistico(
        escenario["est"]["medicina"], desde=timezone.localdate() - timedelta(days=1)
    )
    assert datos["total_atenciones"] == 2  # solo las de exp1, recientes


@pytest.mark.django_db
def test_no_cuenta_atenciones_de_otro_servicio(escenario):
    datos = services.informe_estadistico(escenario["est"]["psicologia"])
    assert datos["total_atenciones"] == 0


# ------------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_la_pantalla_muestra_atenciones_y_personas_por_separado(escenario):
    contenido = (
        _cliente(escenario["medico"]).get(reverse("reportes:informe_servicio")).content.decode()
    )
    assert "Atenciones" in contenido
    assert "Personas atendidas" in contenido
    # Django localiza el separador decimal para es-ec: 66.7 se pinta "66,7".
    assert "66,7%" in contenido  # el porcentaje de "mujer": 2 de 3 atenciones


@pytest.mark.django_db
def test_un_profesional_sin_servicio_no_entra(escenario):
    suelto = Usuario.objects.create_user(
        username="suelto_informe", password=CLAVE, rol_principal=Rol.PROFESIONAL
    )
    respuesta = _cliente(suelto).get(reverse("reportes:informe_servicio"))
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_no_se_puede_pedir_el_informe_de_un_servicio_ajeno(escenario):
    """El médico no puede pedir el informe de Psicología, que no es suyo."""
    psico = escenario["est"]["psicologia"]
    respuesta = _cliente(escenario["medico"]).get(
        reverse("reportes:informe_servicio"), {"servicio": psico.pk}
    )
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_el_pdf_se_genera(escenario):
    respuesta = _cliente(escenario["medico"]).get(reverse("reportes:informe_servicio_pdf"))
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_el_informe_no_esta_gateado_a_direccion(escenario):
    """
    A diferencia del tablero, este informe no exige rol de Dirección: basta
    con pertenecer al servicio. Es la diferencia central con `_solo_directivos`.
    """
    assert (
        _cliente(escenario["medico"]).get(reverse("reportes:informe_servicio")).status_code == 200
    )
