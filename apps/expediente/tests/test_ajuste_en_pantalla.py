"""
El profesional puede ver lo declarado y anotar lo que comprobó.

`AjusteDeServicio` existía entero —modelo, servicio, selectores y hasta el uso
en el informe estadístico— y **ninguna pantalla lo exponía**: era el motor sin
el volante. En consulta se identifica un embarazo que la ficha de matrícula no
declara y el profesional no tenía dónde ponerlo, así que o no se registraba o
alguien acababa editando la base institucional, que es la fuente para todo el
sistema.

Lo que se prueba es la regla, no el formulario: lo anotado vale para el
servicio que lo comprobó, la matrícula queda intacta y se puede volver atrás.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.expediente.models import AjusteDeServicio
from apps.expediente.selectors import valores_efectivos
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, _perfil = crear_profesional("medico_ajuste", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()
    cliente = Client()
    assert cliente.login(username="medico_ajuste", password=CLAVE)
    return {
        "est": est,
        "medico": medico,
        "cliente": cliente,
        "expediente": crear_expediente(cedula="1104567894"),
    }


@pytest.mark.django_db
def test_la_pantalla_ofrece_anotar_lo_comprobado(escenario):
    """Antes no había por dónde: el motor estaba y el volante no."""
    contenido = (
        escenario["cliente"]
        .get(reverse("expediente:detalle", args=[escenario["expediente"].pk]))
        .content.decode()
    )
    assert "comprobó" in contenido
    assert "Embarazo" in contenido
    assert reverse("expediente:ajustar", args=[escenario["expediente"].pk]) in contenido


@pytest.mark.django_db
def test_anotar_un_embarazo_no_toca_la_base_institucional(escenario):
    """
    El caso que lo motiva. La matrícula sigue diciendo lo que decía: es la
    fuente para el resto del sistema y nadie autorizó a reescribirla desde una
    consulta.
    """
    expediente = escenario["expediente"]
    escenario["cliente"].post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "gestacion", "valor": "Sí", "nota": "Confirmada en consulta, 12 semanas"},
        follow=True,
    )

    ajuste = AjusteDeServicio.objects.get(expediente=expediente, variable="gestacion")
    assert ajuste.valor == "Sí"
    assert ajuste.servicio == escenario["est"]["medicina"]

    filas = {f["variable"]: f for f in valores_efectivos(expediente, escenario["est"]["medicina"])}
    assert filas["gestacion"]["valor"] == "Sí"
    assert filas["gestacion"]["institucional"] != "Sí", "la matrícula no debe haber cambiado"


@pytest.mark.django_db
def test_lo_anotado_vale_solo_para_el_servicio_que_lo_comprobo(escenario):
    """Cada servicio reporta lo que él comprobó; lo que no, lo toma de la institución."""
    expediente = escenario["expediente"]
    escenario["cliente"].post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "gestacion", "valor": "Sí"},
        follow=True,
    )
    otro = {f["variable"]: f for f in valores_efectivos(expediente, escenario["est"]["psicologia"])}
    assert otro["gestacion"]["valor"] != "Sí"
    assert otro["gestacion"]["ajustado"] is False


@pytest.mark.django_db
def test_se_puede_volver_a_lo_declarado(escenario):
    """Que se pueda deshacer es lo que hace seguro anotar."""
    expediente = escenario["expediente"]
    url = reverse("expediente:ajustar", args=[expediente.pk])
    escenario["cliente"].post(url, {"variable": "gestacion", "valor": "Sí"}, follow=True)
    escenario["cliente"].post(url, {"variable": "gestacion", "accion": "quitar"}, follow=True)
    assert not AjusteDeServicio.objects.filter(expediente=expediente, variable="gestacion").exists()


@pytest.mark.django_db
def test_no_se_puede_ajustar_el_genero_ni_la_identidad(escenario):
    """
    Son declaraciones de la persona sobre sí misma. Que un servicio las
    «corrigiera» sería asignarle una identidad.
    """
    expediente = escenario["expediente"]
    respuesta = escenario["cliente"].post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "genero", "valor": "otro"},
        follow=True,
    )
    assert not AjusteDeServicio.objects.filter(variable="genero").exists()
    assert "declara" in respuesta.content.decode()


@pytest.mark.django_db
def test_un_formulario_incompleto_avisa_y_no_revienta(escenario):
    """Un `request.POST["variable"]` que no llega es un aviso, no un 500."""
    respuesta = escenario["cliente"].post(
        reverse("expediente:ajustar", args=[escenario["expediente"].pk]), {}, follow=True
    )
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_quien_no_ve_expedientes_no_ajusta(db):
    """El ajuste escribe sobre el expediente: exige el mismo permiso que abrirlo."""
    from apps.usuarios.models import Rol, Usuario

    expediente = crear_expediente(cedula="1712345675")
    Usuario.objects.create_user(username="ajeno", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    cliente = Client()
    assert cliente.login(username="ajeno", password=CLAVE)
    respuesta = cliente.post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "gestacion", "valor": "Sí"},
    )
    assert respuesta.status_code == 403
    assert not AjusteDeServicio.objects.exists()


# --------------------------------------------------- quien atiende en varios


@pytest.fixture
def con_dos_servicios(db):
    """
    Un profesional de Medicina que también atiende en Enfermería.

    No es un caso raro: en la UNL el mismo personal cubre más de una ventanilla.
    """
    from apps.core.models import Servicio

    est = crear_estructura()
    enfermeria, _ = Servicio.objects.get_or_create(
        codigo="enfermeria", defaults={"nombre": "Enfermería", "seccion": est["salud"]}
    )
    usuario, perfil = crear_profesional("poli_ajuste", est["medicina"], est["salud"])
    perfil.servicios.add(enfermeria)
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="poli_ajuste", password=CLAVE)
    return {
        "est": est,
        "enfermeria": enfermeria,
        "cliente": cliente,
        "expediente": crear_expediente(cedula="1712345675"),
    }


@pytest.mark.django_db
def test_quien_atiende_en_varios_servicios_tambien_puede_ajustar(con_dos_servicios):
    """
    Antes no podía: la pantalla exigía UN servicio y, con dos, sencillamente no
    aparecía. El ajuste quedaba fuera del alcance de quien más lo necesita.
    """
    respuesta = con_dos_servicios["cliente"].get(
        reverse("expediente:detalle", args=[con_dos_servicios["expediente"].pk])
    )
    contenido = respuesta.content.decode()

    assert "comprobó" in contenido
    assert "Anotar desde" in contenido
    assert "Enfermería" in contenido


@pytest.mark.django_db
def test_cada_servicio_ve_lo_que_el_comprobo_y_no_lo_del_otro(con_dos_servicios):
    """El ajuste es de quien comprobó: la ventanilla de al lado no lo hereda."""
    expediente = con_dos_servicios["expediente"]
    enfermeria = con_dos_servicios["enfermeria"]
    cliente = con_dos_servicios["cliente"]

    cliente.post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "gestacion", "valor": "Sí", "servicio": enfermeria.pk, "nota": "en consulta"},
    )

    desde_enfermeria = cliente.get(
        reverse("expediente:detalle", args=[expediente.pk]), {"servicio": enfermeria.pk}
    ).content.decode()
    desde_medicina = cliente.get(
        reverse("expediente:detalle", args=[expediente.pk]),
        {"servicio": con_dos_servicios["est"]["medicina"].pk},
    ).content.decode()

    assert "en consulta" in desde_enfermeria
    assert "en consulta" not in desde_medicina


@pytest.mark.django_db
def test_pedir_un_servicio_ajeno_no_ensena_lo_ajeno(con_dos_servicios):
    """
    Un id en la URL no es un permiso. Se cae a un servicio propio en silencio:
    negar por su nombre confirmaría que ese servicio existe y qué id tiene.
    """
    psicologia = con_dos_servicios["est"]["psicologia"]

    respuesta = con_dos_servicios["cliente"].get(
        reverse("expediente:detalle", args=[con_dos_servicios["expediente"].pk]),
        {"servicio": psicologia.pk},
    )

    assert respuesta.status_code == 200
    assert respuesta.context["servicio_de_ajuste"].pk != psicologia.pk
    assert psicologia not in respuesta.context["servicios_de_ajuste"]


@pytest.mark.django_db
def test_con_dos_servicios_el_ajuste_sin_servicio_no_se_adivina(con_dos_servicios):
    """
    Atribuir el hallazgo al primero de la lista es peor que no registrarlo: el
    informe lo reportaría después como comprobado por un servicio que no lo vio.
    """
    respuesta = con_dos_servicios["cliente"].post(
        reverse("expediente:ajustar", args=[con_dos_servicios["expediente"].pk]),
        {"variable": "gestacion", "valor": "Sí"},
        follow=True,
    )

    assert not AjusteDeServicio.objects.exists()
    assert "Indique desde qué servicio" in respuesta.content.decode()


@pytest.mark.django_db
def test_tras_anotar_se_vuelve_al_mismo_servicio(con_dos_servicios):
    """
    Guardar bien y enseñar otra cosa es lo peor de los dos mundos.

    La redirección perdía el servicio, así que el aviso decía «Anotado para
    Medicina» y debajo se veía la tabla de otro servicio con el valor sin tocar:
    parecía que no había guardado, y lo lógico entonces es volver a intentarlo.

    Se anota desde Medicina a propósito, y no desde Enfermería: la lista va por
    nombre, así que el servicio al que se caía por omisión era justamente
    Enfermería y la prueba habría pasado con el defecto puesto.
    """
    medicina = con_dos_servicios["est"]["medicina"]
    respuesta = con_dos_servicios["cliente"].post(
        reverse("expediente:ajustar", args=[con_dos_servicios["expediente"].pk]),
        {"variable": "gestacion", "valor": "Sí", "servicio": medicina.pk, "nota": "en consulta"},
        follow=True,
    )

    assert respuesta.context["servicio_de_ajuste"] == medicina
    assert "en consulta" in respuesta.content.decode()
