"""
La bitácora se puede leer, y leerla no abre una rendija en el sello.

Se registraba todo y no había ninguna pantalla: la única forma de saber quién
abrió un expediente era el shell o el panel de Django. Una bitácora que nadie
puede consultar no rinde cuentas de nada.

Lo delicado es que la bitácora habla de contenido clínico. Una línea que diga
«jorge.perez leyó la atención 47 del expediente de María Pérez, servicio
Psicología» filtra por la puerta de atrás justo lo que el sello protege: que
esa persona es paciente de Psicología.

La regla que fija esto: **el actor siempre se ve; el paciente, no.** Quien
audita ve que alguien de Psicología hizo una lectura y cuándo —que es lo que
hace falta para pedir cuentas— sin ver de quién. El propio servicio sí ve sus
entradas completas, porque para él no hay nada que ocultar.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("med_pant", est["medicina"], est["salud"])
    psicologo, perfil_psico = crear_profesional("psi_pant", est["psicologia"], est["psico"])
    director = Usuario.objects.create_user(
        username="dir_pant", password=CLAVE, rol_principal=Rol.DIRECTOR
    )
    admin = Usuario.objects.create_user(
        username="adm_pant", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )
    estudiante = Usuario.objects.create_user(
        username="est_pant", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    for usuario in (medico, psicologo, director, admin, estudiante):
        usuario.set_password(CLAVE)
        usuario.save()

    expediente = crear_expediente()
    from apps.usuarios.decorators import verificar_acceso_atencion

    LogAuditoria.objects.all().delete()
    verificar_acceso_atencion(medico, crear_atencion(expediente, est["medicina"], perfil_medico))
    verificar_acceso_atencion(
        psicologo, crear_atencion(expediente, est["psicologia"], perfil_psico)
    )
    return {
        "expediente": expediente,
        "medico": medico,
        "psicologo": psicologo,
        "director": director,
        "admin": admin,
        "estudiante": estudiante,
    }


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ---------------------------------------------------------- quién la abre


@pytest.mark.django_db
def test_direccion_y_administracion_la_abren(escenario):
    for usuario in (escenario["director"], escenario["admin"]):
        respuesta = _cliente(usuario).get(reverse("auditoria:bitacora"))
        assert respuesta.status_code == 200, f"{usuario.username} no alcanza la bitácora"


@pytest.mark.django_db
def test_un_estudiante_no(escenario):
    assert _cliente(escenario["estudiante"]).get(reverse("auditoria:bitacora")).status_code == 403


@pytest.mark.django_db
def test_un_profesional_corriente_tampoco(escenario):
    """
    Auditar es una función de gobierno, no de atención. Un profesional que
    pudiera recorrer la bitácora entera sabría quién pasó por cada servicio.
    """
    assert _cliente(escenario["medico"]).get(reverse("auditoria:bitacora")).status_code == 403


# ------------------------------------------------------------- el sello


@pytest.mark.django_db
def test_direccion_ve_el_actor_pero_no_el_paciente_de_una_entrada_sellada(escenario):
    """
    El corazón del asunto. Dirección necesita saber que hubo una lectura en
    Psicología y quién la hizo —eso es rendir cuentas—, pero no de quién.
    """
    respuesta = _cliente(escenario["director"]).get(reverse("auditoria:bitacora"))
    filas = respuesta.context["filas"]

    sellada = [f for f in filas if f["registro"].servicio == "psicologia"]
    assert sellada, "la entrada de Psicología no aparece en absoluto"
    fila = sellada[0]
    assert fila["registro"].usuario == escenario["psicologo"], "no se ve quién miró"
    assert fila["velado"] is True
    assert fila["expediente"] is None, "se está mostrando de quién era"

    abierta = [f for f in filas if f["registro"].servicio == "medicina"][0]
    assert abierta["velado"] is False
    assert abierta["expediente"] is not None


@pytest.mark.django_db
def test_la_pantalla_no_imprime_el_paciente_sellado(escenario):
    contenido = _cliente(escenario["director"]).get(reverse("auditoria:bitacora")).content.decode()
    assert escenario["expediente"].persona.cedula not in contenido or (
        contenido.count(escenario["expediente"].persona.cedula) == 1
    ), "la cédula del paciente sellado se imprimió"


@pytest.mark.django_db
def test_psicologia_ve_sus_propias_entradas_completas(escenario):
    """Para el servicio no hay nada que ocultar: es su propio trabajo."""
    respuesta = _cliente(escenario["psicologo"]).get(reverse("auditoria:bitacora"))
    assert respuesta.status_code == 200, "el servicio no puede auditarse a sí mismo"
    filas = respuesta.context["filas"]
    assert all(
        f["registro"].servicio == "psicologia" for f in filas
    ), "el servicio ve entradas que no son suyas"
    assert filas and filas[0]["velado"] is False


# ------------------------------------------------------------- utilidad


@pytest.mark.django_db
def test_se_filtra_por_usuario_y_por_accion(escenario):
    """Una bitácora sin filtros es un volcado: nadie encuentra nada en ella."""
    cliente = _cliente(escenario["director"])
    respuesta = cliente.get(reverse("auditoria:bitacora"), {"usuario": escenario["medico"].pk})
    filas = respuesta.context["filas"]
    assert filas, "el filtro por usuario no devolvió nada"
    assert all(f["registro"].usuario_id == escenario["medico"].pk for f in filas)

    respuesta = cliente.get(reverse("auditoria:bitacora"), {"accion": "read"})
    assert all(f["registro"].accion == "read" for f in respuesta.context["filas"])


@pytest.mark.django_db
def test_los_rechazos_se_pueden_aislar(escenario):
    """
    Es la consulta que más se va a hacer: quién intentó entrar donde no debía.
    """
    respuesta = _cliente(escenario["director"]).get(
        reverse("auditoria:bitacora"), {"resultado": "denegado"}
    )
    assert respuesta.status_code == 200
    assert all(f["registro"].resultado == "denegado" for f in respuesta.context["filas"])


# ------------------------------------ el velo depende de que se declare


def test_todo_registro_sobre_una_atencion_declara_su_servicio():
    """
    El velo de la bitácora se decide por el campo `servicio`. Un registro que
    apunte a contenido clínico y no lo declare se pinta como si fuera abierto,
    y entonces la pantalla de auditoría enseña al paciente de una firma de
    Psicología. Pasó: los seis registros de `firma` traían el expediente y no
    el servicio.

    No se puede comprobar en tiempo de ejecución sin adivinar, así que se
    comprueba en el código: quien escribe un registro con `atencion` a la vista
    declara de qué servicio es.
    """
    import ast
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[3]
    olvidos = []
    for archivo in sorted(raiz.glob("apps/*/*.py")):
        if "/tests/" in str(archivo) or archivo.name == "registro.py":
            continue
        try:
            arbol = ast.parse(archivo.read_text())
        except SyntaxError:  # pragma: no cover
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            if "LogAuditoria.objects.create" not in ast.unparse(nodo.func):
                continue
            claves = {k.arg for k in nodo.keywords}
            fuente = ast.unparse(nodo)
            # Solo importa si el registro se refiere a una atención: es lo
            # único que puede pertenecer a un servicio confidencial.
            if "atencion" in fuente and "servicio" not in claves:
                olvidos.append(f"{archivo.relative_to(raiz)}:{nodo.lineno}")
    assert olvidos == [], (
        "registros de bitácora sobre una atención que no declaran su servicio "
        f"—la pantalla los mostraría sin velar—: {olvidos}"
    )


@pytest.mark.django_db
def test_una_firma_de_psicologia_no_delata_al_paciente(escenario):
    """La consecuencia concreta del invariante de arriba."""
    from apps.auditoria.models import LogAuditoria

    LogAuditoria.objects.create(
        usuario=escenario["psicologo"],
        accion=LogAuditoria.Accion.SIGN,
        modulo="firma",
        entidad="SolicitudFirma",
        entidad_id="1",
        expediente_id=escenario["expediente"].pk,
        servicio="psicologia",
    )
    filas = _cliente(escenario["director"]).get(reverse("auditoria:bitacora")).context["filas"]
    firma = [f for f in filas if f["registro"].accion == LogAuditoria.Accion.SIGN][0]
    assert firma["velado"] is True
    assert firma["expediente"] is None
