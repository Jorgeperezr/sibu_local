"""
Abrir una historia clínica tiene que dejar rastro. Y un intento rechazado, más.

`LogAuditoria.Accion` define `READ` desde el primer sprint y se usaba en UN
sitio —el portal—, así que abrir el expediente de alguien no dejaba constancia.
Contra el abuso interno, impedir el acceso es media defensa; la otra mitad es
que quede escrito quién miró.

Lo delicado es el rechazo. `verificar_acceso_atencion` lanza `PermissionDenied`
y `ATOMIC_REQUESTS = True` envuelve toda la petición en una transacción: un log
escrito dentro se va con el rollback y el intento fallido no deja rastro. Es la
trampa que CLAUDE.md señala y que ya costó dos veces. Por eso el rechazo se
anota desde el middleware, que corre FUERA del bloque atómico de la vista.
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("med_aud", est["medicina"], est["salud"])
    psicologo, perfil_psico = crear_profesional("psi_aud", est["psicologia"], est["psico"])
    for usuario in (medico, psicologo):
        usuario.set_password(CLAVE)
        usuario.save()
    expediente = crear_expediente()
    return {
        "est": est,
        "medico": medico,
        "psicologo": psicologo,
        "expediente": expediente,
        "atencion_med": crear_atencion(expediente, est["medicina"], perfil_medico),
        "atencion_psi": crear_atencion(expediente, est["psicologia"], perfil_psico),
    }


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------ la lectura


@pytest.mark.django_db
def test_leer_una_atencion_deja_registro(escenario):
    from apps.usuarios.decorators import verificar_acceso_atencion

    LogAuditoria.objects.all().delete()
    verificar_acceso_atencion(escenario["medico"], escenario["atencion_med"])

    registro = LogAuditoria.objects.filter(accion=LogAuditoria.Accion.READ).first()
    assert registro is not None, "leer una atención no dejó rastro"
    assert registro.usuario == escenario["medico"]
    assert registro.entidad_id == str(escenario["atencion_med"].pk)
    assert registro.expediente_id == escenario["expediente"].pk
    assert registro.resultado == "ok"


@pytest.mark.django_db
def test_el_registro_dice_de_qué_servicio_era(escenario):
    """
    Sin el servicio no se puede aplicar el sello a la propia bitácora: haría
    falta abrir cada atención para saber si la entrada es confidencial, y eso
    sería otra lectura del contenido sellado.
    """
    from apps.usuarios.decorators import verificar_acceso_atencion

    LogAuditoria.objects.all().delete()
    verificar_acceso_atencion(escenario["psicologo"], escenario["atencion_psi"])

    registro = LogAuditoria.objects.filter(accion=LogAuditoria.Accion.READ).first()
    assert registro.servicio == "psicologia"


# ------------------------------------------------------------- el rechazo


@pytest.mark.django_db
def test_un_intento_rechazado_queda_apuntado_para_el_middleware(escenario):
    """
    El médico intenta abrir contenido de Psicología: se le niega y queda
    apuntado. Apuntado y no escrito, a propósito: escribirlo aquí lo borraría
    el rollback que provoca el `PermissionDenied` de la línea siguiente. Quien
    lo escribe es el middleware, y eso lo comprueba la prueba de abajo por HTTP.
    """
    from apps.auditoria.middleware import get_auditoria_context
    from apps.auditoria.registro import volcar_rechazos
    from apps.usuarios.decorators import verificar_acceso_atencion

    LogAuditoria.objects.all().delete()
    with pytest.raises(PermissionDenied):
        verificar_acceso_atencion(escenario["medico"], escenario["atencion_psi"])

    # Sin petición en curso no hay transacción que revierta nada, así que se
    # escribe en el acto: diferirlo aquí solo serviría para que nadie lo
    # escribiera nunca. Dentro de una petición sí se difiere, y eso lo
    # comprueba la prueba de abajo por HTTP.
    assert not get_auditoria_context().get("en_peticion")
    assert volcar_rechazos() == 0, "no debería haber nada pendiente fuera de una petición"
    registro = LogAuditoria.objects.filter(resultado="denegado").first()
    assert registro is not None
    assert registro.usuario == escenario["medico"]
    assert registro.servicio == "psicologia"


@pytest.mark.django_db(transaction=True)
def test_el_rechazo_sobrevive_al_rollback_de_la_peticion(escenario):
    """
    La prueba que fija la trampa, por la vía real: un POST completo.

    `ATOMIC_REQUESTS = True` envuelve la vista en una transacción y
    `PermissionDenied` la aborta. Un log escrito dentro de la vista se iría con
    el rollback. `transaction=True` en la prueba desactiva el envoltorio de
    pytest para que el rollback sea el de verdad y no el del banco de pruebas:
    sin eso, esta prueba pasaría aunque el registro se escribiera dentro.
    """
    LogAuditoria.objects.all().delete()
    cliente = _cliente(escenario["medico"])
    respuesta = cliente.get(reverse("expediente:detalle", args=[escenario["expediente"].pk]))
    assert respuesta.status_code == 200

    # Y ahora el intento contra el contenido sellado, por su pantalla.
    from apps.psicologia.models import FichaPsicologica

    ficha = FichaPsicologica.objects.create(
        atencion=escenario["atencion_psi"], motivo="Primera entrevista"
    )
    respuesta = cliente.get(reverse("psicologia:proceso", args=[ficha.pk]))
    assert respuesta.status_code == 403

    denegados = LogAuditoria.objects.filter(resultado="denegado")
    assert denegados.exists(), "el intento rechazado no sobrevivió al rollback de la petición"
    assert denegados.first().usuario == escenario["medico"]
