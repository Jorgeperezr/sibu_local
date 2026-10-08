"""
Ajustes por servicio: corregir un dato sin reescribir la base institucional.

La base viene de la matrícula y es una foto del día en que el estudiante llenó
la ficha. Un servicio encuentra otra realidad —la ficha dice que no hay embarazo
y en Medicina se registra uno— y necesita anotarlo para trabajar y para su
informe, sin tocar la fuente que usa el resto del sistema.

Dos reglas que estas pruebas fijan por encima de todo:

1. El ajuste vale SOLO dentro del servicio que lo hizo. Otro servicio sigue
   viendo la matrícula, y su informe también.
2. El género y la identidad u orientación sexual NO se ajustan desde ningún
   servicio: son declaraciones de la persona sobre sí misma, y «corregirlas»
   desde una consulta sería asignarle una identidad a alguien.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.expediente.models import AjusteDeServicio, AlertaClinica
from apps.expediente.selectors import valores_efectivos
from apps.expediente.services import quitar_ajuste, registrar_ajuste, registrar_alerta
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)

CLAVE = "clave-larga-12345"
V = AjusteDeServicio.Variable


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("med_ajuste", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()
    psicologo, perfil_psico = crear_profesional("psi_ajuste", est["psicologia"], est["psico"])
    expediente = crear_expediente(cedula="1104567894")
    cliente = Client()
    assert cliente.login(username="med_ajuste", password=CLAVE)
    return {
        "est": est,
        "medico": medico,
        "perfil_medico": perfil_medico,
        "perfil_psico": perfil_psico,
        "exp": expediente,
        "cliente": cliente,
    }


def _fila(expediente, servicio, variable):
    return next(f for f in valores_efectivos(expediente, servicio) if f["variable"] == variable)


# ----------------------------------------------------- el caso que lo motivó


@pytest.mark.django_db
def test_medicina_registra_un_embarazo_que_la_matricula_no_traia(escenario):
    antes = _fila(escenario["exp"], escenario["est"]["medicina"], V.GESTACION)
    assert antes["institucional"] == "No"

    registrar_ajuste(
        escenario["exp"],
        escenario["est"]["medicina"],
        V.GESTACION,
        "Sí",
        usuario=escenario["medico"],
        nota="Detectado en consulta del 4 de septiembre",
    )

    despues = _fila(escenario["exp"], escenario["est"]["medicina"], V.GESTACION)
    assert despues["valor"] == "Sí"
    assert despues["ajustado"] is True
    # Y la matrícula sigue diciendo lo que decía: se ve al lado, para revisar.
    assert despues["institucional"] == "No"


@pytest.mark.django_db
def test_el_ajuste_no_alcanza_a_otro_servicio(escenario):
    """
    Es el punto entero del alcance por servicio: cada uno trabaja con lo que él
    comprobó, y lo que no, con lo que dice la institución.
    """
    registrar_ajuste(
        escenario["exp"],
        escenario["est"]["medicina"],
        V.GESTACION,
        "Sí",
        usuario=escenario["medico"],
    )
    otra = _fila(escenario["exp"], escenario["est"]["psicologia"], V.GESTACION)
    assert otra["valor"] == "No"
    assert otra["ajustado"] is False


@pytest.mark.django_db
def test_el_ajuste_no_reescribe_la_base_institucional(escenario):
    """
    La base es la fuente para el resto del sistema y nadie autorizó a
    corregirla desde una consulta.
    """
    registrar_ajuste(
        escenario["exp"],
        escenario["est"]["medicina"],
        V.DISCAPACIDAD_TIPO,
        "Física",
        usuario=escenario["medico"],
    )
    escenario["exp"].refresh_from_db()
    assert escenario["exp"].discapacidad_tipo == ""


@pytest.mark.django_db
def test_deshacer_devuelve_el_dato_de_matricula(escenario):
    """
    Poder volver atrás es lo que hace seguro ajustar: sin esto una corrección
    equivocada quedaría fija para siempre en ese servicio.
    """
    medicina = escenario["est"]["medicina"]
    registrar_ajuste(escenario["exp"], medicina, V.GESTACION, "Sí", usuario=escenario["medico"])
    assert quitar_ajuste(escenario["exp"], medicina, V.GESTACION, usuario=escenario["medico"])
    assert _fila(escenario["exp"], medicina, V.GESTACION)["valor"] == "No"


@pytest.mark.django_db
def test_reajustar_reemplaza_en_vez_de_acumular(escenario):
    medicina = escenario["est"]["medicina"]
    registrar_ajuste(escenario["exp"], medicina, V.GESTACION, "Sí", usuario=escenario["medico"])
    registrar_ajuste(escenario["exp"], medicina, V.GESTACION, "No", usuario=escenario["medico"])
    assert AjusteDeServicio.objects.filter(expediente=escenario["exp"]).count() == 1
    assert _fila(escenario["exp"], medicina, V.GESTACION)["valor"] == "No"


# -------------------------------------------- lo que no se ajusta, y por qué


@pytest.mark.django_db
@pytest.mark.parametrize("variable", ["genero", "identidad_orientacion_sexual"])
def test_el_genero_y_la_identidad_no_se_ajustan_desde_un_servicio(escenario, variable):
    """
    Son declaraciones de la persona sobre sí misma. Que un servicio las
    «corrigiera» sería asignarle una identidad a alguien.
    """
    with pytest.raises(ValidationError, match="lo declara la propia persona"):
        registrar_ajuste(
            escenario["exp"],
            escenario["est"]["medicina"],
            variable,
            "Otro",
            usuario=escenario["medico"],
        )
    assert not AjusteDeServicio.objects.exists()


@pytest.mark.django_db
def test_no_estan_entre_las_variables_ajustables(escenario):
    """No basta con rechazarlas: no deben ni ofrecerse en la pantalla."""
    ofrecidas = {f["variable"] for f in valores_efectivos(escenario["exp"], None)}
    assert "genero" not in ofrecidas
    assert "identidad_orientacion_sexual" not in ofrecidas


@pytest.mark.django_db
def test_una_variable_inventada_se_rechaza(escenario):
    with pytest.raises(ValidationError, match="no ajustable"):
        registrar_ajuste(
            escenario["exp"],
            escenario["est"]["medicina"],
            "sueldo",
            "1000",
            usuario=escenario["medico"],
        )


@pytest.mark.django_db
def test_un_porcentaje_ilegible_se_rechaza_aqui(escenario):
    """Mismo criterio que el alta: no en forma de error de base más adelante."""
    with pytest.raises(ValidationError, match="no puede pasar de 100"):
        registrar_ajuste(
            escenario["exp"],
            escenario["est"]["medicina"],
            V.DISCAPACIDAD_PORCENTAJE,
            "150",
            usuario=escenario["medico"],
        )


# ------------------------------------------------------ el informe lo recoge


@pytest.mark.django_db
def test_el_informe_del_servicio_cuenta_lo_que_el_servicio_comprobo(escenario):
    """
    Sin esto el informe contaría la foto del día de la matrícula y no lo que el
    servicio sabe, que es justo lo que se pidió.
    """
    from apps.reportes.services import informe_estadistico

    medicina = escenario["est"]["medicina"]
    crear_atencion(escenario["exp"], medicina, escenario["perfil_medico"])

    sin_ajuste = informe_estadistico(medicina)
    assert sin_ajuste["embarazo"]["total"] == 0

    registrar_ajuste(escenario["exp"], medicina, V.GESTACION, "Sí", usuario=escenario["medico"])
    con_ajuste = informe_estadistico(medicina)
    assert con_ajuste["embarazo"]["total"] == 1
    assert con_ajuste["embarazo"]["porcentaje"] == 100.0


@pytest.mark.django_db
def test_un_no_del_servicio_tambien_manda_en_su_informe(escenario):
    """
    Si aquí se comprobó que la gestación terminó, seguir contándola inflaría el
    informe con algo que este servicio sabe que ya no es cierto.
    """
    from apps.reportes.services import informe_estadistico

    medicina = escenario["est"]["medicina"]
    crear_atencion(escenario["exp"], medicina, escenario["perfil_medico"])
    registrar_alerta(escenario["exp"], AlertaClinica.Tipo.GESTACION, "Declarada en matrícula")
    assert informe_estadistico(medicina)["embarazo"]["total"] == 1

    registrar_ajuste(escenario["exp"], medicina, V.GESTACION, "No", usuario=escenario["medico"])
    assert informe_estadistico(medicina)["embarazo"]["total"] == 0


@pytest.mark.django_db
def test_el_ajuste_de_un_servicio_no_altera_el_informe_de_otro(escenario):
    from apps.reportes.services import informe_estadistico

    medicina = escenario["est"]["medicina"]
    psicologia = escenario["est"]["psicologia"]
    crear_atencion(escenario["exp"], medicina, escenario["perfil_medico"])
    crear_atencion(escenario["exp"], psicologia, escenario["perfil_psico"])

    registrar_ajuste(escenario["exp"], medicina, V.GESTACION, "Sí", usuario=escenario["medico"])
    assert informe_estadistico(medicina)["embarazo"]["total"] == 1
    assert informe_estadistico(psicologia)["embarazo"]["total"] == 0


# ------------------------------------------------------------------ pantalla


@pytest.mark.django_db
def test_la_pantalla_muestra_los_dos_valores(escenario):
    registrar_ajuste(
        escenario["exp"],
        escenario["est"]["medicina"],
        V.GESTACION,
        "Sí",
        usuario=escenario["medico"],
        nota="Detectado en consulta",
    )
    contenido = (
        escenario["cliente"]
        .get(reverse("expediente:datos", args=[escenario["exp"].pk]))
        .content.decode()
    )
    assert "Según matrícula" in contenido
    assert "ajustado aquí" in contenido
    assert "Detectado en consulta" in contenido


@pytest.mark.django_db
def test_la_pantalla_dice_que_la_identidad_no_se_ajusta(escenario):
    contenido = (
        escenario["cliente"]
        .get(reverse("expediente:datos", args=[escenario["exp"].pk]))
        .content.decode()
    )
    assert "solo se declara, no se ajusta" in contenido


@pytest.mark.django_db
def test_se_ajusta_desde_la_pantalla(escenario):
    escenario["cliente"].post(
        reverse("expediente:datos", args=[escenario["exp"].pk]),
        {"servicio": "medicina", "variable": V.GESTACION, "valor": "Sí", "nota": "En consulta"},
    )
    ajuste = AjusteDeServicio.objects.get(expediente=escenario["exp"])
    assert ajuste.servicio.codigo == "medicina"
    assert ajuste.valor == "Sí"


@pytest.mark.django_db
def test_no_se_ajusta_desde_un_servicio_ajeno(escenario):
    """
    El ajuste vale dentro de un servicio, así que hacerlo desde fuera no
    significaría nada. Se cae al primer servicio propio, no al pedido.
    """
    escenario["cliente"].post(
        reverse("expediente:datos", args=[escenario["exp"].pk]),
        {"servicio": "psicologia", "variable": V.GESTACION, "valor": "Sí"},
    )
    ajuste = AjusteDeServicio.objects.get(expediente=escenario["exp"])
    assert ajuste.servicio.codigo == "medicina"


@pytest.mark.django_db
def test_la_pantalla_exige_permiso_de_expediente(escenario):
    from apps.usuarios.models import Rol, Usuario

    Usuario.objects.create_user(username="curioso", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    cliente = Client()
    assert cliente.login(username="curioso", password=CLAVE)
    url = reverse("expediente:datos", args=[escenario["exp"].pk])
    assert cliente.get(url).status_code == 403
    assert cliente.post(url, {"variable": V.GESTACION, "valor": "Sí"}).status_code == 403


@pytest.mark.django_db
def test_el_ajuste_queda_auditado(escenario):
    from apps.auditoria.models import LogAuditoria

    registrar_ajuste(
        escenario["exp"],
        escenario["est"]["medicina"],
        V.GESTACION,
        "Sí",
        usuario=escenario["medico"],
    )
    log = LogAuditoria.objects.filter(entidad="AjusteDeServicio").first()
    assert log is not None
    assert log.detalle["servicio"] == "medicina"
    assert log.detalle["variable"] == V.GESTACION
