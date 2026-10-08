"""
Firma electrónica con FirmaEC.

El foco está en el endpoint de retorno: FirmaEC lo invoca desde su servidor, sin
sesión ni CSRF. Lo único que lo protege es la API Key y las validaciones. Si
alguien lo alcanza, escribe en el expediente de un paciente.
"""

import base64
import json
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.firma import services
from apps.firma.models import FirmaDocumento, SolicitudFirma
from apps.firma.providers import get_provider

PDF = b"%PDF-1.4 contenido de prueba"
CLAVE_CALLBACK = "clave-callback-de-prueba"


def _certificado(cedula="1104567894", **extra):
    base = {
        "emitidoPara": "JORGE PEREZ",
        "emitidoPor": "Security Data",
        "cedula": cedula,
        "entidadCertificadora": "Security Data",
        "serial": "0123456789",
        "certificadoVigente": True,
        "certificadoDigitalValido": True,
        "integridadFirma": True,
    }
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def firmaec_activo(settings):
    """
    Las pruebas del callback exigen el proveedor FirmaEC.

    El defecto del sistema es "deshabilitada": un despliegue sin configurar no
    debe exponer el endpoint de retorno.
    """
    settings.FIRMA_PROVIDER = "firmaec"
    settings.FIRMAEC_SERVICIO_URL = "https://impws.firmadigital.gob.ec/servicio"
    settings.FIRMAEC_SISTEMA = "sibu"
    settings.FIRMAEC_API_KEY = "k"
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    u, prof = crear_profesional("medico", est["medicina"], est["salud"])
    u.cedula = "1104567894"
    u.save(update_fields=["cedula"])
    exp = crear_expediente(cedula="1712345675")
    atencion = Atencion.objects.create(
        expediente=exp, servicio=est["medicina"], profesional=prof, fecha_hora=timezone.now()
    )
    solicitud = services.preparar_solicitud(
        atencion=atencion,
        solicitante=u,
        pdf=PDF,
        documento_ref_tipo="atencion",
        documento_ref_id=atencion.pk,
    )
    return {"est": est, "u": u, "prof": prof, "exp": exp, "atencion": atencion, "s": solicitud}


def _callback(correlacion, *, cedula="1104567894", api_key=CLAVE_CALLBACK, **campos):
    cuerpo = {
        "cedula": cedula,
        "nombreDocumento": f"SIBU-{correlacion}.pdf",
        "archivo": base64.b64encode(b"%PDF-1.4 firmado").decode(),
        "firmasValidas": True,
        "integridadDocumento": True,
        "error": "null",
        "certificado": [_certificado(cedula)],
    }
    cuerpo.update(campos)
    return Client().post(
        "/grabar_archivos_firmados",
        data=json.dumps(cuerpo),
        content_type="application/json",
        headers={"x-api-key": api_key},
    )


# --------------------------------------------------------------------------
# El camino feliz
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_solicitud_no_guarda_la_clave_privada_ni_la_contrasena(escenario):
    """SIBU solo custodia el PDF: nada del certificado del usuario."""
    campos = {f.name for f in SolicitudFirma._meta.get_fields()}
    for prohibido in ("password", "clave", "contrasena", "p12", "llave_privada"):
        assert not any(prohibido in c for c in campos), f"El modelo expone '{prohibido}'"


@pytest.mark.django_db
def test_callback_valido_asienta_la_firma(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback(escenario["s"].correlacion)
    assert r.status_code == 200
    assert r.content.decode() == "OK"  # el manual exige exactamente esto

    escenario["s"].refresh_from_db()
    assert escenario["s"].estado == SolicitudFirma.Estado.FIRMADA
    firma = FirmaDocumento.objects.get(documento_ref_id=escenario["atencion"].pk)
    assert firma.firmante_nombre == "JORGE PEREZ"
    assert firma.entidad_certificadora == "Security Data"
    assert firma.hash_documento == escenario["s"].hash_firmado


@pytest.mark.django_db
def test_la_firma_queda_auditada(escenario, settings):
    from apps.auditoria.models import LogAuditoria

    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    _callback(escenario["s"].correlacion)
    log = LogAuditoria.objects.filter(accion=LogAuditoria.Accion.SIGN).first()
    assert log is not None
    assert log.expediente_id == escenario["exp"].pk
    assert log.detalle["firmante"] == "JORGE PEREZ"


# --------------------------------------------------------------------------
# El endpoint expuesto
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_sin_api_key_no_entra(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback(escenario["s"].correlacion, api_key="")
    assert r.status_code == 403
    escenario["s"].refresh_from_db()
    assert escenario["s"].estado != SolicitudFirma.Estado.FIRMADA


@pytest.mark.django_db
def test_api_key_incorrecta_no_entra(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    assert _callback(escenario["s"].correlacion, api_key="otra-clave").status_code == 403


@pytest.mark.django_db
def test_si_no_hay_api_key_configurada_se_rechaza_todo(escenario, settings):
    """Un despliegue mal configurado no puede quedar abierto de par en par."""
    settings.FIRMAEC_CALLBACK_API_KEY = ""
    assert _callback(escenario["s"].correlacion, api_key="").status_code == 403


@pytest.mark.django_db
def test_correlacion_inventada_no_crea_nada(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback("correlacion-que-no-existe")
    assert r.status_code == 400
    assert FirmaDocumento.objects.count() == 0


@pytest.mark.django_db
def test_nombre_de_documento_ajeno_se_rechaza(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = Client().post(
        "/grabar_archivos_firmados",
        data=json.dumps({"cedula": "1104567894", "nombreDocumento": "cualquier-cosa.pdf"}),
        content_type="application/json",
        headers={"x-api-key": CLAVE_CALLBACK},
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_otra_cedula_no_puede_firmar_el_documento_ajeno(escenario, settings):
    """
    El firmante tiene que ser quien pidió firmar. Sin esto, cualquier titular de
    un certificado válido podría firmar el informe de otro profesional.
    """
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback(escenario["s"].correlacion, cedula="0999999999")
    assert r.status_code == 400
    escenario["s"].refresh_from_db()
    assert escenario["s"].estado == SolicitudFirma.Estado.FALLIDA
    assert FirmaDocumento.objects.count() == 0


@pytest.mark.django_db
def test_firma_invalida_no_se_guarda(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback(escenario["s"].correlacion, firmasValidas=False)
    assert r.status_code == 400
    assert FirmaDocumento.objects.count() == 0


@pytest.mark.django_db
def test_integridad_rota_no_se_guarda(escenario, settings):
    """Si la firma no cubre todo el documento, el PDF pudo alterarse después."""
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback(escenario["s"].correlacion, integridadDocumento=False)
    assert r.status_code == 400
    assert FirmaDocumento.objects.count() == 0


@pytest.mark.django_db
def test_certificado_no_vigente_se_rechaza(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback(
        escenario["s"].correlacion,
        certificado=[_certificado(certificadoVigente=False)],
    )
    assert r.status_code == 400
    assert FirmaDocumento.objects.count() == 0


@pytest.mark.django_db
def test_archivo_que_no_es_pdf_se_rechaza(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback(
        escenario["s"].correlacion,
        archivo=base64.b64encode(b"<?php system($_GET[0]); ?>").decode(),
    )
    assert r.status_code == 400
    assert FirmaDocumento.objects.count() == 0


@pytest.mark.django_db
def test_reenvio_no_duplica_la_firma(escenario, settings):
    """FirmaEC podría reintentar: la segunda vez no debe sobrescribir nada."""
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    assert _callback(escenario["s"].correlacion).status_code == 200
    assert _callback(escenario["s"].correlacion).status_code == 400
    assert FirmaDocumento.objects.count() == 1


@pytest.mark.django_db
def test_get_no_es_aceptado(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    assert Client().get("/grabar_archivos_firmados").status_code == 405


# --------------------------------------------------------------------------
# El sello de Psicología frente a un firmador externo
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_psicologia_no_sale_a_un_firmador_externo(escenario, settings):
    """
    Firmar manda el PDF fuera de SIBU. Con FirmaEC centralizado, un informe
    psicológico saldría además de la UNL. El RBAC no lo impediría: la fuga
    sería por una tubería legítima.
    """
    settings.FIRMAEC_DESCENTRALIZADO_PROPIO = False
    psico = Servicio.objects.get(codigo="psicologia")
    u, prof = crear_profesional("psicologo", psico, psico.seccion)
    # Cédula distinta de la del médico: `Usuario.cedula` es única.
    u.cedula = "1101002002"
    u.save(update_fields=["cedula"])
    atencion = Atencion.objects.create(
        expediente=escenario["exp"], servicio=psico, profesional=prof, fecha_hora=timezone.now()
    )
    with pytest.raises(ValidationError, match="confidencial"):
        services.preparar_solicitud(
            atencion=atencion,
            solicitante=u,
            pdf=PDF,
            documento_ref_tipo="atencion",
            documento_ref_id=atencion.pk,
        )


@pytest.mark.django_db
def test_psicologia_si_el_firmador_es_de_la_institucion(escenario, settings):
    """Con FirmaEC descentralizado propio, el contenido no sale de la UNL."""
    settings.FIRMAEC_DESCENTRALIZADO_PROPIO = True
    psico = Servicio.objects.get(codigo="psicologia")
    u, prof = crear_profesional("psicologo2", psico, psico.seccion)
    u.cedula = "1103004006"
    u.save(update_fields=["cedula"])
    atencion = Atencion.objects.create(
        expediente=escenario["exp"], servicio=psico, profesional=prof, fecha_hora=timezone.now()
    )
    solicitud = services.preparar_solicitud(
        atencion=atencion,
        solicitante=u,
        pdf=PDF,
        documento_ref_tipo="atencion",
        documento_ref_id=atencion.pk,
    )
    assert solicitud.pk


# --------------------------------------------------------------------------
# Reglas de negocio
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_se_firma_dos_veces_el_mismo_documento(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    _callback(escenario["s"].correlacion)
    with pytest.raises(ValidationError, match="ya fue firmado"):
        services.preparar_solicitud(
            atencion=escenario["atencion"],
            solicitante=escenario["u"],
            pdf=PDF,
            documento_ref_tipo="atencion",
            documento_ref_id=escenario["atencion"].pk,
        )


@pytest.mark.django_db
def test_solicitud_repetida_reutiliza_la_abierta(escenario):
    otra = services.preparar_solicitud(
        atencion=escenario["atencion"],
        solicitante=escenario["u"],
        pdf=PDF,
        documento_ref_tipo="atencion",
        documento_ref_id=escenario["atencion"].pk,
    )
    assert otra.pk == escenario["s"].pk


@pytest.mark.django_db
def test_sin_cedula_en_el_perfil_no_se_puede_firmar(escenario):
    u, prof = crear_profesional(
        "sincedula", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    prof.cedula = ""
    prof.save()
    atencion = Atencion.objects.create(
        expediente=escenario["exp"],
        servicio=escenario["est"]["medicina"],
        profesional=prof,
        fecha_hora=timezone.now(),
    )
    with pytest.raises(ValidationError, match="cédula"):
        services.preparar_solicitud(
            atencion=atencion,
            solicitante=u,
            pdf=PDF,
            documento_ref_tipo="atencion",
            documento_ref_id=atencion.pk,
        )


@pytest.mark.django_db
def test_el_enlace_firmaec_lleva_el_token_y_no_el_pdf(escenario, settings):
    """El PDF nunca viaja por la URL: solo el JWT."""
    settings.FIRMAEC_PREPRODUCCION = True
    with patch("apps.firma.client.crear_documento", return_value="aaa.bbb.ccc"):
        inicio = services.iniciar_firma(escenario["s"])
    enlace = inicio.enlace
    assert inicio.tipo == "enlace"
    assert enlace.startswith("firmaec://sibu/firmar?")
    assert "token=aaa.bbb.ccc" in enlace
    assert "tipo_certificado=2" in enlace
    assert "pre=true" in enlace
    assert base64.b64encode(PDF).decode()[:20] not in enlace
    escenario["s"].refresh_from_db()
    assert escenario["s"].estado == SolicitudFirma.Estado.ENVIADA


@pytest.mark.django_db
def test_las_solicitudes_vencidas_se_expiran(escenario, settings):
    escenario["s"].estado = SolicitudFirma.Estado.ENVIADA
    escenario["s"].token_expira_en = timezone.now() - timezone.timedelta(minutes=1)
    escenario["s"].save()
    assert services.expirar_vencidas() == 1
    escenario["s"].refresh_from_db()
    assert escenario["s"].estado == SolicitudFirma.Estado.EXPIRADA


@pytest.mark.django_db
def test_una_solicitud_expirada_ya_no_admite_firma(escenario, settings):
    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    escenario["s"].estado = SolicitudFirma.Estado.EXPIRADA
    escenario["s"].save()
    assert _callback(escenario["s"].correlacion).status_code == 400
    assert FirmaDocumento.objects.count() == 0


@pytest.mark.django_db
def test_el_rechazo_queda_auditado(escenario, settings):
    """
    Regresión: el registro del rechazo vivía dentro del atomic, así que el
    ValidationError que aborta la operación lo revertía y los intentos
    fallidos no dejaban rastro. En una historia clínica son justamente los que
    hay que poder auditar.
    """
    from apps.auditoria.models import LogAuditoria

    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    _callback(escenario["s"].correlacion, cedula="0999999999")

    log = LogAuditoria.objects.filter(
        accion=LogAuditoria.Accion.SIGN, resultado="rechazado"
    ).first()
    assert log is not None, "El intento rechazado no dejó rastro en la auditoría"
    assert "cédula" in log.detalle["motivo"]
    escenario["s"].refresh_from_db()
    assert escenario["s"].estado == SolicitudFirma.Estado.FALLIDA


@pytest.mark.django_db
def test_url_de_servicio_no_https_se_rechaza(escenario, settings):
    """urlopen acepta file://: una URL mal configurada leería el disco."""
    from django.core.exceptions import ImproperlyConfigured

    from apps.firma import client

    for mala in ("file:///etc/passwd", "http://evil.example.com/servicio"):
        settings.FIRMAEC_SERVICIO_URL = mala
        with pytest.raises(ImproperlyConfigured, match="https"):
            client.crear_documento(cedula="1104567894", nombre="x.pdf", pdf=PDF)


# --------------------------------------------------------------------------
# La firma como pieza intercambiable y opcional
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_por_defecto_se_firma_en_el_computador_del_profesional(settings):
    """
    El defecto ya no es "sin firmador", sino el firmador local.

    Antes era "deshabilitada" porque el único firmador implementado, FirmaEC,
    exige registro ante el MINTEL. Al descartarse esa vía, el flujo institucional
    pasa a ser: SIBU genera el PDF, el profesional lo descarga y lo firma en su
    computador. Eso no depende de ningún servicio externo, así que un despliegue
    recién instalado ya puede firmar.

    "deshabilitada" sigue existiendo para quien no quiera firma en absoluto.
    """
    from apps.firma.providers import get_provider

    del settings.FIRMA_PROVIDER
    proveedor = get_provider()
    assert proveedor.codigo == "local"
    assert proveedor.disponible() is True
    assert proveedor.externo is False


@pytest.mark.django_db
def test_el_firmador_deshabilitado_sigue_disponible_como_opcion(settings):
    """Apagar la firma por completo tiene que seguir siendo posible."""
    from apps.firma.providers import get_provider

    settings.FIRMA_PROVIDER = "deshabilitada"
    proveedor = get_provider()
    assert proveedor.disponible() is False
    assert "no está habilitada" in proveedor.motivo_no_disponible()


@pytest.mark.django_db
def test_firmaec_sin_configurar_no_esta_disponible(settings):
    """Faltando credenciales, se avisa: no se intenta y falla a mitad."""
    from apps.firma.providers import get_provider

    settings.FIRMA_PROVIDER = "firmaec"
    settings.FIRMAEC_API_KEY = ""
    proveedor = get_provider()
    assert proveedor.disponible() is False
    assert "FIRMAEC_API_KEY" in proveedor.motivo_no_disponible()


@pytest.mark.django_db
def test_firmador_desconocido_se_detecta(settings):
    from apps.firma.providers import get_provider

    settings.FIRMA_PROVIDER = "inventado"
    with pytest.raises(ValidationError, match="no existe"):
        get_provider()


@pytest.mark.django_db
def test_sin_firmador_no_se_puede_iniciar_pero_el_pdf_existe(escenario, settings):
    """Apagar el firmador no apaga el documento."""
    settings.FIRMA_PROVIDER = "deshabilitada"
    with pytest.raises(ValidationError, match="no está habilitada"):
        services.iniciar_firma(escenario["s"])
    escenario["s"].refresh_from_db()
    # La solicitud sigue abierta y el PDF sin firmar sigue disponible.
    assert escenario["s"].abierta
    assert bytes(escenario["s"].pdf_original).startswith(b"%PDF-")


@pytest.mark.django_db
def test_el_callback_no_existe_si_el_firmador_no_es_firmaec(escenario, settings):
    """No se acepta el retorno de un firmador que esta instalación no usa."""
    settings.FIRMA_PROVIDER = "deshabilitada"
    r = _callback(escenario["s"].correlacion)
    assert r.status_code == 404
    assert FirmaDocumento.objects.count() == 0


@pytest.mark.django_db
def test_un_firmador_interno_si_puede_firmar_psicologia(escenario, settings):
    """
    La política pregunta "¿sale de la institución?", no "¿es FirmaEC?".

    Un firmador interno no plantea el problema del sello, se llame como se
    llame.
    """
    from apps.firma.policy import verificar_puede_salir_a_firmar
    from apps.firma.providers import FirmadorProvider

    class FirmadorInterno(FirmadorProvider):
        codigo, nombre, externo = "interno", "Firmador interno", False

        def disponible(self):
            return True

        def motivo_no_disponible(self):
            return ""

        def nombre_archivo(self, solicitud):
            return solicitud.nombre_documento

        def iniciar(self, solicitud):
            raise NotImplementedError

    settings.FIRMAEC_DESCENTRALIZADO_PROPIO = False
    psico = Servicio.objects.get(codigo="psicologia")
    atencion = Atencion.objects.create(
        expediente=escenario["exp"],
        servicio=psico,
        profesional=escenario["prof"],
        fecha_hora=timezone.now(),
    )
    # Con un firmador externo, denegado.
    with pytest.raises(ValidationError, match="confidencial"):
        verificar_puede_salir_a_firmar(atencion, proveedor=get_provider())
    # Con uno interno, permitido: el contenido no sale.
    verificar_puede_salir_a_firmar(atencion, proveedor=FirmadorInterno())


@pytest.mark.django_db
def test_el_rechazo_del_callback_queda_auditado(escenario, settings):
    """
    Un intento de firma rechazado tiene que dejar rastro, y dejarlo de verdad.

    `_registrar_rechazo` escribe el log y el llamador lanza ValidationError
    acto seguido: es justo la secuencia que CLAUDE.md señala como trampa —
    auditar y abortar en la misma transacción revierte el propio log—. Con
    `ATOMIC_REQUESTS = True` toda la petición es una transacción, así que lo
    único que salva el registro es que el endpoint capture el error en vez de
    dejarlo escapar. Esta prueba fija esa garantía por la vía real, el POST.

    Las pruebas de rechazo vecinas comprueban que la firma no se guarda; esta
    comprueba lo contrario: que lo que sí debe guardarse, se guarda.
    """
    from apps.auditoria.models import LogAuditoria

    settings.FIRMAEC_CALLBACK_API_KEY = CLAVE_CALLBACK
    r = _callback(escenario["s"].correlacion, firmasValidas=False)
    assert r.status_code == 400  # respuesta controlada, no un 500

    log = LogAuditoria.objects.filter(
        modulo="firma", resultado="rechazado", entidad_id=str(escenario["s"].pk)
    ).first()
    assert log is not None, "el intento de firma rechazado no quedó auditado"
    assert "no son válidas" in log.detalle["motivo"]


@pytest.mark.django_db
def test_la_cedula_del_firmante_sale_de_la_cuenta(escenario, settings):
    """
    Se leía de `solicitante.perfil.cedula`, un campo que NO existe: fuera de
    las pruebas —que lo tapaban asignando el atributo en memoria— devolvía
    siempre "" y con FirmaEC la firma no habría arrancado nunca. La cédula del
    profesional vive en `Usuario.cedula`.

    La cuenta se relee de la base a propósito: un atributo puesto en memoria
    no sobreviviría al refresh, así que esta prueba no puede pasar por accidente.
    """
    est = escenario["est"]
    u, prof = crear_profesional("medico_cedula", est["medicina"], est["salud"])
    atencion = Atencion.objects.create(
        expediente=escenario["exp"],
        servicio=est["medicina"],
        profesional=prof,
        fecha_hora=timezone.now(),
    )
    # Sin cédula en la cuenta, FirmaEC no deja preparar la solicitud.
    with pytest.raises(ValidationError, match="cédula"):
        services.preparar_solicitud(
            atencion=atencion,
            solicitante=u,
            pdf=PDF,
            documento_ref_tipo="atencion",
            documento_ref_id=atencion.pk,
        )

    u.cedula = "1105006009"
    u.save(update_fields=["cedula"])
    u.refresh_from_db()
    solicitud = services.preparar_solicitud(
        atencion=atencion,
        solicitante=u,
        pdf=PDF,
        documento_ref_tipo="atencion",
        documento_ref_id=atencion.pk,
    )
    assert solicitud.cedula_solicitante == "1105006009"
