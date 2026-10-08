"""
Exportar el historial de atenciones a una hoja de cálculo compartida.

Lo que se pidió: pegar el enlace de una hoja de Google compartida con permiso
de editor y que el sistema vuelque ahí las atenciones.

Lo que eso implica, y por qué el diseño es el que es:

- **El contenido sale del control de SIBU.** Una vez en la hoja, ni
  `puede_ver_atencion` ni la bitácora alcanzan: quien tenga el enlace lo lee, y
  el sistema no puede saber quién lo hizo ni revocarlo.
- **Con permiso de editor, además se puede modificar**, así que la hoja deja de
  ser un registro fiel de lo que pasó. Es una copia de trabajo, no un
  documento.

El proyecto ya resolvió este mismo caso en `referir_a_externo`: un servicio
confidencial no emite referencias externas «porque el resumen saldría de la
Unidad». La exportación aplica la misma regla, y estas pruebas la fijan.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.reportes import exportacion

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_med = crear_profesional("med_exp", est["medicina"], est["salud"])
    psicologo, perfil_psi = crear_profesional("psi_exp", est["psicologia"], est["psico"])
    from apps.usuarios.models import Rol, Usuario

    director = Usuario.objects.create_user(
        username="dir_exp", password=CLAVE, rol_principal=Rol.DIRECTOR
    )
    expediente = crear_expediente()
    return {
        "est": est,
        "medico": medico,
        "psicologo": psicologo,
        "director": director,
        "expediente": expediente,
        "at_med": crear_atencion(expediente, est["medicina"], perfil_med),
        "at_psi": crear_atencion(expediente, est["psicologia"], perfil_psi),
    }


# ------------------------------------------------------------------ el sello


@pytest.mark.django_db
def test_las_atenciones_de_psicologia_no_salen_nunca(escenario):
    """
    Ni siquiera para el propio servicio. La regla del sello es «no accesible
    FUERA del servicio», y una hoja de cálculo compartida es fuera: es el mismo
    razonamiento que impide a Psicología emitir referencias externas.
    """
    for quien in (escenario["director"], escenario["psicologo"], escenario["medico"]):
        filas = exportacion.historial(quien)
        servicios = {f["Servicio"] for f in filas}
        assert "Psicología" not in servicios, f"salió contenido sellado para {quien.username}"


@pytest.mark.django_db
def test_la_exportacion_dice_cuántas_atenciones_retuvo(escenario):
    """
    Una exportación parcial que no avisa de que es parcial es peor que ninguna:
    quien la reciba contará mal y no sabrá que le faltan filas.
    """
    # Se mira desde Psicología, que es quien tiene algo retenido: para su
    # propio servicio la exportación no produce NADA, y lo dice.
    resumen = exportacion.resumen_de_exportacion(escenario["psicologo"])
    assert resumen["exportables"] == 0
    assert resumen["retenidas_por_confidencialidad"] == 1

    # Y Medicina exporta lo suyo sin nada retenido.
    del_medico = exportacion.resumen_de_exportacion(escenario["medico"])
    assert del_medico["exportables"] == 1
    assert del_medico["retenidas_por_confidencialidad"] == 0


# ------------------------------------------------------- qué se exporta y qué no


@pytest.mark.django_db
def test_no_se_exporta_texto_clinico(escenario):
    """
    Fecha, servicio, profesional y a quién se atendió: eso es gestión y es lo
    que sirve para un informe. El motivo de consulta, los diagnósticos y las
    notas son el contenido del expediente, y en una hoja editable dejan de
    tener dueño.
    """
    escenario["at_med"].motivo_consulta = "Cefalea con antecedente de migraña"
    escenario["at_med"].save(update_fields=["motivo_consulta"])

    filas = exportacion.historial(escenario["medico"])
    assert filas
    volcado = " ".join(str(v) for f in filas for v in f.values())
    assert "migraña" not in volcado, "se exportó texto clínico"
    assert "Medicina" in volcado
    assert escenario["expediente"].persona.cedula in volcado


@pytest.mark.django_db
def test_cada_quien_exporta_lo_que_puede_ver(escenario):
    """
    La exportación no es una puerta trasera al RBAC: si un profesional no ve
    una atención en pantalla, tampoco la exporta.
    """
    from apps.core.models import Servicio

    odonto = Servicio.objects.create(
        codigo="odontologia", nombre="Odontología", seccion=escenario["est"]["salud"]
    )
    otro, perfil = crear_profesional("odo_exp", odonto, escenario["est"]["salud"])
    crear_atencion(escenario["expediente"], odonto, perfil)

    del_odontologo = {f["Servicio"] for f in exportacion.historial(otro)}
    assert del_odontologo == {"Odontología"}, del_odontologo


# ------------------------------------------------------- el enlace de la hoja


@pytest.mark.parametrize(
    "enlace,esperado",
    [
        ("https://docs.google.com/spreadsheets/d/1AbC_dEF-123/edit#gid=0", "1AbC_dEF-123"),
        ("https://docs.google.com/spreadsheets/d/1AbC_dEF-123/edit?usp=sharing", "1AbC_dEF-123"),
        ("https://docs.google.com/spreadsheets/d/1AbC_dEF-123", "1AbC_dEF-123"),
        ("1AbC_dEF-123", "1AbC_dEF-123"),
    ],
)
def test_se_acepta_el_enlace_tal_como_se_copia_del_navegador(enlace, esperado):
    """
    Quien comparte una hoja copia la barra de direcciones entera. Exigirle que
    extraiga el identificador a mano es pedirle que haga de intérprete.
    """
    assert exportacion.id_de_hoja(enlace) == esperado


@pytest.mark.parametrize(
    "enlace",
    ["", "https://example.com/algo", "https://docs.google.com/document/d/1abc/edit", "   "],
)
def test_un_enlace_que_no_es_una_hoja_se_rechaza_con_su_motivo(enlace):
    with pytest.raises(ValidationError, match="hoja de cálculo de Google"):
        exportacion.id_de_hoja(enlace)


# ------------------------------------------------- el proveedor, intercambiable


def test_sin_credenciales_el_proveedor_lo_dice_en_vez_de_reventar(settings):
    """
    Mismo patrón que Drive, firma y el proveedor académico: la integración
    externa no está lista y el sistema tiene que funcionar igual. Lo que no
    puede es fallar con un traceback al pulsar el botón.
    """
    settings.SIBU = {**getattr(settings, "SIBU", {}), "GOOGLE_CREDENCIALES_JSON": ""}
    proveedor = exportacion.get_proveedor()
    assert proveedor.disponible() is False
    assert "credenciales" in proveedor.motivo_no_disponible().lower()


@pytest.mark.django_db
def test_direccion_no_exporta_el_detalle_de_atenciones(escenario):
    """
    No es un olvido: `rbac.atenciones_visibles` le devuelve cero a quien
    gobierna, por separación de funciones —«los tableros muestran gestión, no
    contenido»—. Dirección tiene el tablero y su CSV de agregados; el historial
    lo exporta cada servicio sobre su propio trabajo.
    """
    assert exportacion.historial(escenario["director"]) == []


# ---------------------------------------------------------------- la pantalla


@pytest.mark.django_db
def test_la_pantalla_la_abre_quien_atiende(escenario):
    from django.test import Client
    from django.urls import reverse

    escenario["medico"].set_password(CLAVE)
    escenario["medico"].save()
    cliente = Client()
    assert cliente.login(username="med_exp", password=CLAVE)

    respuesta = cliente.get(reverse("reportes:exportar_hoja"))
    assert respuesta.status_code == 200
    assert respuesta.context["resumen"]["exportables"] == 1


@pytest.mark.django_db
def test_la_pantalla_avisa_de_lo_que_implica_compartir_la_hoja(escenario):
    """
    Quien pulsa el botón tiene que saber que a partir de ahí SIBU no controla
    nada: ni quién lo lee, ni que no se modifique, ni poder revocarlo.
    """
    from django.test import Client
    from django.urls import reverse

    escenario["medico"].set_password(CLAVE)
    escenario["medico"].save()
    cliente = Client()
    assert cliente.login(username="med_exp", password=CLAVE)

    contenido = cliente.get(reverse("reportes:exportar_hoja")).content.decode().lower()
    assert "fuera de sibu" in contenido or "deja de" in contenido
    assert "editor" in contenido


@pytest.mark.django_db
def test_un_estudiante_no_exporta_nada(escenario):
    from django.test import Client
    from django.urls import reverse

    from apps.usuarios.models import Rol, Usuario

    Usuario.objects.create_user(username="est_exp", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    cliente = Client()
    assert cliente.login(username="est_exp", password=CLAVE)
    assert cliente.get(reverse("reportes:exportar_hoja")).status_code == 403


@pytest.mark.django_db
def test_volcar_queda_auditado(escenario, monkeypatch):
    """
    Sacar el historial de la Unidad es de las cosas que más falta hace poder
    revisar después: quién lo hizo, cuándo, cuántas filas y a qué hoja.
    """
    from django.test import Client
    from django.urls import reverse

    from apps.auditoria.models import LogAuditoria

    class Falso:
        codigo = "falso"

        def disponible(self):
            return True

        def motivo_no_disponible(self):
            return ""

        def volcar(self, hoja_id, encabezados, filas):
            return f"https://docs.google.com/spreadsheets/d/{hoja_id}/edit"

    monkeypatch.setattr(exportacion, "get_proveedor", lambda: Falso())
    escenario["medico"].set_password(CLAVE)
    escenario["medico"].save()
    cliente = Client()
    assert cliente.login(username="med_exp", password=CLAVE)

    LogAuditoria.objects.all().delete()
    cliente.post(
        reverse("reportes:exportar_hoja"),
        {"enlace": "https://docs.google.com/spreadsheets/d/1AbC_dEF-123/edit"},
    )
    registro = LogAuditoria.objects.filter(accion=LogAuditoria.Accion.EXPORT).first()
    assert registro is not None, "el volcado no quedó auditado"
    assert registro.usuario == escenario["medico"]
    assert registro.detalle["filas"] == 1
    assert registro.detalle["hoja"] == "1AbC_dEF-123"


@pytest.mark.django_db
def test_se_descarga_el_mismo_historial_en_csv(escenario):
    """
    Sin credenciales de Google la pantalla no puede volcar, y ofrecer un CSV
    que no existe sería mandar al usuario a un botón inexistente. El CSV lleva
    exactamente las mismas filas y el mismo filtro: es la misma exportación por
    otro camino, no una puerta más ancha.
    """
    from django.test import Client
    from django.urls import reverse

    escenario["medico"].set_password(CLAVE)
    escenario["medico"].save()
    cliente = Client()
    assert cliente.login(username="med_exp", password=CLAVE)

    respuesta = cliente.get(reverse("reportes:exportar_hoja"), {"formato": "csv"})
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"].startswith("text/csv")
    texto = respuesta.content.decode("utf-8-sig")
    assert "Servicio" in texto
    assert "Medicina" in texto
    assert "Psicología" not in texto, "el CSV se saltó el sello"


@pytest.mark.django_db
def test_la_descarga_csv_tambien_queda_auditada(escenario):
    from django.test import Client
    from django.urls import reverse

    from apps.auditoria.models import LogAuditoria

    escenario["medico"].set_password(CLAVE)
    escenario["medico"].save()
    cliente = Client()
    assert cliente.login(username="med_exp", password=CLAVE)

    LogAuditoria.objects.all().delete()
    cliente.get(reverse("reportes:exportar_hoja"), {"formato": "csv"})
    registro = LogAuditoria.objects.filter(accion=LogAuditoria.Accion.EXPORT).first()
    assert registro is not None, "la descarga no quedó auditada"
    assert registro.detalle["formato"] == "csv"
