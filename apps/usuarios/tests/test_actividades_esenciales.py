"""
Actividades esenciales del manual de puestos.

El manual real numera entre diez y trece actividades; la última suele ser
"las demás que asigne el jefe inmediato", bajo la cual se acumulan tareas
concretas delegadas. Se prueba la numeración por lista propia (no una
numeración global que un borrado dejaría con huecos), que borrar una
actividad se lleva sus sub-actividades, y que nadie edita la lista de otro
profesional.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import ActividadEsencial
from apps.usuarios.services import agregar_actividad, eliminar_actividad

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    usuario, perfil = crear_profesional("medico_actividades", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    return {"est": est, "usuario": usuario, "perfil": perfil}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_las_actividades_se_numeran_en_orden(escenario):
    a1 = agregar_actividad(escenario["perfil"], "Atender consulta médica")
    a2 = agregar_actividad(escenario["perfil"], "Registrar la historia clínica")
    assert a1.orden == 1
    assert a2.orden == 2


@pytest.mark.django_db
def test_una_descripcion_vacia_se_rechaza(escenario):
    with pytest.raises(ValidationError, match="descripción"):
        agregar_actividad(escenario["perfil"], "   ")


@pytest.mark.django_db
def test_las_subactividades_se_numeran_dentro_de_su_propia_lista(escenario):
    """
    La última actividad ("las demás que asigne el jefe") acumula
    sub-actividades con su propia numeración, no la general: la tercera
    sub-actividad es la "3" de su lista, no la "13" de la lista completa.
    """
    for i in range(1, 11):
        agregar_actividad(escenario["perfil"], f"Actividad {i}")
    ultima = agregar_actividad(
        escenario["perfil"], "Las demás actividades que le asigne su jefe inmediato"
    )
    assert ultima.orden == 11

    sub1 = agregar_actividad(escenario["perfil"], "Cubrir turnos de emergencia", ultima)
    sub2 = agregar_actividad(escenario["perfil"], "Apoyar campañas de salud", ultima)
    assert sub1.orden == 1
    assert sub2.orden == 2
    assert list(ultima.subactividades.all()) == [sub1, sub2]


@pytest.mark.django_db
def test_una_actividad_superior_de_otro_perfil_se_rechaza(escenario):
    otro, otro_perfil = crear_profesional(
        "otro_medico_act", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    ajena = agregar_actividad(otro_perfil, "Actividad de otro profesional")
    with pytest.raises(ValidationError, match="no pertenece a este perfil"):
        agregar_actividad(escenario["perfil"], "Intento de sub-actividad ajena", ajena)


@pytest.mark.django_db
def test_eliminar_una_actividad_se_lleva_sus_subactividades(escenario):
    principal = agregar_actividad(escenario["perfil"], "Las demás que asigne el jefe")
    sub = agregar_actividad(escenario["perfil"], "Tarea delegada", principal)
    eliminar_actividad(principal)
    assert not ActividadEsencial.objects.filter(pk=sub.pk).exists()


# ------------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_agregar_una_actividad_desde_la_pantalla(escenario):
    cliente = _cliente(escenario["usuario"])
    cliente.post(
        reverse("usuarios:mi_perfil"),
        {"accion": "agregar_actividad", "descripcion": "Atender consulta médica"},
    )
    actividad = ActividadEsencial.objects.get(perfil=escenario["perfil"])
    assert actividad.descripcion == "Atender consulta médica"
    assert actividad.orden == 1


@pytest.mark.django_db
def test_agregar_una_subactividad_desde_la_pantalla(escenario):
    principal = agregar_actividad(escenario["perfil"], "Las demás que asigne el jefe")
    cliente = _cliente(escenario["usuario"])
    cliente.post(
        reverse("usuarios:mi_perfil"),
        {
            "accion": "agregar_subactividad",
            "actividad_superior": principal.pk,
            "descripcion": "Cubrir turnos de emergencia",
        },
    )
    sub = ActividadEsencial.objects.get(actividad_superior=principal)
    assert sub.descripcion == "Cubrir turnos de emergencia"


@pytest.mark.django_db
def test_eliminar_una_actividad_desde_la_pantalla(escenario):
    actividad = agregar_actividad(escenario["perfil"], "Actividad a borrar")
    cliente = _cliente(escenario["usuario"])
    cliente.post(
        reverse("usuarios:mi_perfil"),
        {"accion": "eliminar_actividad", "actividad": actividad.pk},
    )
    assert not ActividadEsencial.objects.filter(pk=actividad.pk).exists()


@pytest.mark.django_db
def test_no_se_puede_agregar_subactividad_bajo_la_de_otro_profesional(escenario):
    """
    Es la comprobación de acceso, no la del servicio: la vista busca la
    actividad superior FILTRADA por el perfil propio, así que una ajena da
    404 antes de llegar a `agregar_actividad`.
    """
    otro, otro_perfil = crear_profesional(
        "otro_medico_act_web", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    ajena = agregar_actividad(otro_perfil, "Actividad de otro profesional")
    respuesta = _cliente(escenario["usuario"]).post(
        reverse("usuarios:mi_perfil"),
        {
            "accion": "agregar_subactividad",
            "actividad_superior": ajena.pk,
            "descripcion": "Intento cruzado",
        },
    )
    assert respuesta.status_code == 404
    assert not ActividadEsencial.objects.filter(descripcion="Intento cruzado").exists()


@pytest.mark.django_db
def test_no_se_puede_eliminar_una_actividad_de_otro_profesional(escenario):
    otro, otro_perfil = crear_profesional(
        "otro_medico_act_del", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    ajena = agregar_actividad(otro_perfil, "Actividad de otro profesional")
    respuesta = _cliente(escenario["usuario"]).post(
        reverse("usuarios:mi_perfil"),
        {"accion": "eliminar_actividad", "actividad": ajena.pk},
    )
    assert respuesta.status_code == 404
    assert ActividadEsencial.objects.filter(pk=ajena.pk).exists()


@pytest.mark.django_db
def test_la_pantalla_lista_las_actividades_con_su_jerarquia(escenario):
    principal = agregar_actividad(escenario["perfil"], "Las demás que asigne el jefe")
    agregar_actividad(escenario["perfil"], "Cubrir turnos de emergencia", principal)
    contenido = _cliente(escenario["usuario"]).get(reverse("usuarios:mi_perfil")).content.decode()
    assert "Las demás que asigne el jefe" in contenido
    assert "Cubrir turnos de emergencia" in contenido
