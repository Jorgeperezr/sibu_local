"""
Tres defectos del camino clínico, encontrados usando el sistema.

1. **Abrir una consulta creaba una atención NUEVA cada vez.** Pulsar «Consulta
   médica», volver atrás y volver a pulsar dejaba dos historias clínicas en
   blanco en el expediente de la misma persona. Comprobado contra una portable
   real: tres entradas seguidas dejaron tres historias (ids 2, 3 y 4). Y una
   historia clínica no se borra: queda ahí y hay que explicar de dónde salió.

2. **El motivo de consulta no se podía escribir.** `motivo_consulta` solo se
   rellenaba desde un POST al abrir la consulta, y el expediente abría con un
   enlace —un GET—, así que llegaba siempre vacío. En la pantalla el campo
   estaba `disabled`. Resultado: un hueco gris en la historia clínica justo
   donde va por qué vino la persona, sin forma de llenarlo.

3. **Una atención firmada se podía reescribir.** El modelo dice «Una atención
   firmada es inmutable; las correcciones se hacen por enmienda» y nadie lo
   comprobaba al escribir. Las plantillas ponen `disabled`, que es una cortesía
   del navegador: un POST con los campos dentro reescribía el documento
   firmado. Una firma sobre algo que después cambia no vale nada.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.models import CIE10
from apps.expediente.models import Atencion
from apps.expediente.services import borrador_abierto, exigir_atencion_editable
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.medicina import services as med
from apps.medicina.models import AtencionMedicina

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    usuario, perfil = crear_profesional("medica", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    return {
        "est": est,
        "usuario": usuario,
        "perfil": perfil,
        "exp": crear_expediente(cedula="1104346091"),
    }


# ------------------------------------------------- no se duplica la historia


@pytest.mark.django_db
def test_entrar_dos_veces_no_abre_dos_historias(escenario, client):
    client.login(username="medica", password=CLAVE)
    destino = reverse("medicina:iniciar", args=[escenario["exp"].pk])

    client.post(destino)
    client.post(destino)
    client.post(destino)

    assert Atencion.objects.filter(expediente=escenario["exp"]).count() == 1


@pytest.mark.django_db
def test_se_vuelve_a_la_misma_historia_empezada(escenario, client):
    """No basta con no duplicar: hay que llevar a la que ya estaba escrita."""
    client.login(username="medica", password=CLAVE)
    destino = reverse("medicina:iniciar", args=[escenario["exp"].pk])

    primera = client.post(destino)
    segunda = client.post(destino)

    assert primera.headers["Location"] == segunda.headers["Location"]


@pytest.mark.django_db
def test_una_atencion_cerrada_no_se_reaprovecha(escenario):
    """
    Si la persona vuelve otro día, eso es una atención nueva. Reaprovechar la
    anterior reescribiría la historia.
    """
    hc = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo="Cefalea"
    )
    hc.atencion.estado = Atencion.Estado.CERRADA
    hc.atencion.save(update_fields=["estado"])

    assert (
        borrador_abierto(
            escenario["exp"], escenario["est"]["medicina"], escenario["perfil"], "medicina"
        )
        is None
    )


@pytest.mark.django_db
def test_el_borrador_de_otro_profesional_no_es_el_mio(escenario):
    """Dos profesionales del mismo servicio atienden por separado."""
    med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo="Cefalea"
    )
    _, otra = crear_profesional("medico2", escenario["est"]["medicina"], escenario["est"]["salud"])

    assert (
        borrador_abierto(escenario["exp"], escenario["est"]["medicina"], otra, "medicina") is None
    )


@pytest.mark.django_db
def test_una_atencion_sin_historia_colgada_no_rompe_la_pantalla(escenario):
    """
    Una fila de `Atencion` creada por otro camino no tiene `AtencionMedicina`:
    devolverla mandaría la pantalla a un id que no existe.
    """
    from django.utils import timezone

    Atencion.objects.create(
        expediente=escenario["exp"],
        servicio=escenario["est"]["medicina"],
        profesional=escenario["perfil"],
        fecha_hora=timezone.now(),
        estado=Atencion.Estado.BORRADOR,
    )

    assert (
        borrador_abierto(
            escenario["exp"], escenario["est"]["medicina"], escenario["perfil"], "medicina"
        )
        is None
    )


# ----------------------------------------------------- el motivo se escribe


@pytest.mark.django_db
def test_el_motivo_de_consulta_se_puede_escribir(escenario, client):
    client.login(username="medica", password=CLAVE)
    hc = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo=""
    )

    client.post(
        reverse("medicina:consulta", args=[hc.pk]),
        {
            "accion": "guardar",
            "motivo_consulta": "Dolor de cabeza de tres días",
            "enfermedad_actual": "Cefalea frontal",
            "plan_tratamiento": "",
            "indicaciones": "",
        },
    )

    hc.atencion.refresh_from_db()
    assert hc.atencion.motivo_consulta == "Dolor de cabeza de tres días"


@pytest.mark.django_db
def test_el_motivo_guardado_se_vuelve_a_ver(escenario, client):
    """
    El campo estaba `disabled`: aunque se hubiera guardado por otro camino, lo
    que se veía era un hueco gris. Lo que se guarda tiene que APARECER.
    """
    client.login(username="medica", password=CLAVE)
    hc = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo="Control anual"
    )

    contenido = client.get(reverse("medicina:consulta", args=[hc.pk])).content.decode()

    assert "Control anual" in contenido
    assert 'name="motivo_consulta"' in contenido, "sin name, el campo no se envía"


# --------------------------------------------- una firma no se puede borrar


@pytest.mark.django_db
def test_una_atencion_firmada_no_se_reescribe(escenario, client):
    """
    El POST llega igual aunque la plantilla ponga `disabled`: eso lo decide el
    navegador, no el servidor.
    """
    client.login(username="medica", password=CLAVE)
    hc = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo="Cefalea"
    )
    hc.enfermedad_actual = "Lo que firmó"
    hc.save()
    hc.atencion.estado = Atencion.Estado.FIRMADA
    hc.atencion.save(update_fields=["estado"])

    respuesta = client.post(
        reverse("medicina:consulta", args=[hc.pk]),
        {
            "accion": "guardar",
            "motivo_consulta": "otro motivo",
            "enfermedad_actual": "Lo que alguien metió después",
            "plan_tratamiento": "",
            "indicaciones": "",
        },
        follow=True,
    )

    hc.refresh_from_db()
    hc.atencion.refresh_from_db()
    assert hc.enfermedad_actual == "Lo que firmó", "se reescribió una historia firmada"
    assert hc.atencion.motivo_consulta == "Cefalea"
    assert "no se puede modificar" in respuesta.content.decode()


@pytest.mark.django_db
def test_un_borrador_si_se_edita(escenario):
    """La regla protege lo firmado, no entorpece lo que se está escribiendo."""
    hc = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo="Cefalea"
    )

    exigir_atencion_editable(hc.atencion)  # no lanza


@pytest.mark.django_db
def test_la_regla_vale_para_una_enmendada(escenario):
    hc = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo="Cefalea"
    )
    hc.atencion.estado = Atencion.Estado.ENMENDADA
    hc.atencion.save(update_fields=["estado"])

    with pytest.raises(ValidationError, match="enmienda"):
        exigir_atencion_editable(hc.atencion)


@pytest.mark.django_db
def test_el_diagnostico_ya_estaba_protegido_en_su_servicio(escenario):
    """
    Por qué el agujero era SOLO el guardado directo.

    `agregar_diagnostico` ya comprobaba la inmutabilidad —lo hace el servicio—,
    igual que recetar y pedir exámenes. Lo que no pasaba por ningún servicio
    era el «Guardar» de la anamnesis: la vista escribía los campos a mano
    sobre el modelo. Esta prueba fija ese reparto para que, si alguien mueve
    el guardia de la vista, quede claro qué dejaba de cubrir.

    Al falsificar quitando el guardia de la vista, esta prueba NO falla: la
    protege su propio servicio. Por eso no basta con ella.
    """
    CIE10.objects.get_or_create(
        codigo="J00", defaults={"descripcion": "Rinofaringitis aguda (resfriado común)"}
    )
    hc = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo="Cefalea"
    )
    hc.atencion.estado = Atencion.Estado.FIRMADA
    hc.atencion.save(update_fields=["estado"])

    with pytest.raises(ValidationError, match="firmada"):
        med.agregar_diagnostico(hc.atencion, "J00", tipo="definitivo")

    assert not hc.atencion.diagnosticos.exists()


@pytest.mark.django_db
def test_la_historia_sigue_siendo_de_quien_la_abrio(escenario):
    """Que no se duplique no puede cambiar de quién es la atención."""
    hc = med.crear_atencion_medicina(
        expediente=escenario["exp"], profesional=escenario["perfil"], motivo="Cefalea"
    )

    assert AtencionMedicina.objects.get(pk=hc.pk).atencion.profesional == escenario["perfil"]


# ------------------------------------- abrir una atención no es un enlace


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ruta",
    ["medicina:iniciar", "odontologia:iniciar", "psicologia:iniciar", "psicopedagogia:iniciar"],
)
def test_abrir_una_atencion_no_responde_a_un_get(escenario, client, ruta):
    """
    Abrir una atención ESCRIBE. Con un GET bastaba un
    `<img src="/medicina/iniciar/37/">` en cualquier página que abriera un
    profesional para dejar una historia clínica a su nombre sobre alguien a
    quien no ha visto. Es lo mismo que ya pasó con cerrar sesión.
    """
    client.login(username="medica", password=CLAVE)
    antes = Atencion.objects.count()

    respuesta = client.get(reverse(ruta, args=[escenario["exp"].pk]))

    assert respuesta.status_code == 405, "sigue creando por GET"
    assert Atencion.objects.count() == antes


@pytest.mark.django_db
def test_el_expediente_abre_la_atencion_con_un_formulario(escenario, client):
    """
    El arreglo va en la PLANTILLA. Si se deja el enlace y se endurece la
    vista, el botón responde 405 y la pantalla queda rota.
    """
    client.login(username="medica", password=CLAVE)

    contenido = client.get(
        reverse("expediente:detalle", args=[escenario["exp"].pk])
    ).content.decode()
    destino = reverse("medicina:iniciar", args=[escenario["exp"].pk])

    assert f'<form method="post" action="{destino}"' in contenido
    assert f'href="{destino}"' not in contenido, "quedó el enlace que hace GET"
