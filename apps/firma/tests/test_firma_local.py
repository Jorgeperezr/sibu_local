"""
Firma en el computador del profesional.

SIBU genera el PDF y lo entrega; el profesional lo firma con su certificado y
decide si lo sube de vuelta al expediente o se lo queda. La criptografía nunca
toca el servidor: por eso lo que se asienta es una firma electrónica simple y
no una digital con certificado verificado.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
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
PDF_FIRMADO = b"%PDF-1.4 contenido firmado por el profesional"
CLAVE = "clave-larga-12345"


def _solicitud(atencion, usuario):
    return services.preparar_solicitud(
        atencion=atencion,
        solicitante=usuario,
        pdf=PDF,
        documento_ref_tipo="atencion",
        documento_ref_id=atencion.pk,
    )


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    u, prof = crear_profesional("medico_local", est["medicina"], est["salud"])
    u.set_password(CLAVE)
    u.save()

    u_otro, _ = crear_profesional("ajeno", est["psicologia"], est["psico"])
    u_otro.set_password(CLAVE)
    u_otro.save()

    exp = crear_expediente(cedula="1712345675")
    atencion = Atencion.objects.create(
        expediente=exp, servicio=est["medicina"], profesional=prof, fecha_hora=timezone.now()
    )
    return {"est": est, "u": u, "exp": exp, "atencion": atencion, "s": _solicitud(atencion, u)}


# ------------------------------------------------------------------ proveedor


@pytest.mark.django_db
def test_el_proveedor_por_defecto_es_el_local_y_esta_disponible():
    """No depende de ningún servicio externo: si el sistema levanta, funciona."""
    proveedor = get_provider()
    assert proveedor.codigo == "local"
    assert proveedor.disponible() is True
    assert proveedor.externo is False


# --------------------------------------------------------------------- subida


@pytest.mark.django_db
def test_subir_el_pdf_firmado_lo_asienta_en_el_expediente(escenario):
    c = Client()
    c.login(username="medico_local", password=CLAVE)
    r = c.post(
        f"/firma/subir-firmado/{escenario['s'].pk}/",
        {"documento": _archivo(PDF_FIRMADO)},
    )
    assert r.status_code == 302

    escenario["s"].refresh_from_db()
    assert escenario["s"].estado == SolicitudFirma.Estado.FIRMADA
    assert bytes(escenario["s"].pdf_firmado) == PDF_FIRMADO

    firma = FirmaDocumento.objects.get(solicitud=escenario["s"])
    # Simple, no digital: SIBU no vio el certificado, así que no puede afirmarlo.
    assert firma.tipo_firma == FirmaDocumento.TipoFirma.ELECTRONICA
    assert firma.entidad_certificadora == ""

    log = LogAuditoria.objects.filter(modulo="firma", accion=LogAuditoria.Accion.SIGN).first()
    assert log is not None
    assert log.detalle["certificado_verificado"] is False


@pytest.mark.django_db
def test_un_archivo_que_no_es_pdf_se_rechaza(escenario):
    with pytest.raises(ValidationError, match="no es un PDF"):
        services.asentar_firma_subida(escenario["s"], b"esto es un .exe", escenario["u"])
    escenario["s"].refresh_from_db()
    assert escenario["s"].estado != SolicitudFirma.Estado.FIRMADA


@pytest.mark.django_db
def test_no_se_asienta_dos_veces_la_misma_solicitud(escenario):
    services.asentar_firma_subida(escenario["s"], PDF_FIRMADO, escenario["u"])
    with pytest.raises(ValidationError, match="ya tiene un documento firmado"):
        services.asentar_firma_subida(escenario["s"], PDF_FIRMADO, escenario["u"])
    assert FirmaDocumento.objects.filter(solicitud=escenario["s"]).count() == 1


@pytest.mark.django_db
def test_un_profesional_de_otro_servicio_no_sube_al_expediente_ajeno(escenario):
    """Sin RBAC en la vista se subiría un documento al expediente de otro."""
    c = Client()
    c.login(username="ajeno", password=CLAVE)
    r = c.post(
        f"/firma/subir-firmado/{escenario['s'].pk}/",
        {"documento": _archivo(PDF_FIRMADO)},
    )
    assert r.status_code == 403
    escenario["s"].refresh_from_db()
    assert escenario["s"].estado != SolicitudFirma.Estado.FIRMADA


# ---------------------------------------------------------------- psicología


@pytest.mark.django_db
def test_psicologia_si_puede_firmar_en_local(escenario):
    """
    El sello no se rompe: se cumple por otra vía.

    Con FirmaEC el informe psicológico sale hacia un servicio de terceros, y por
    eso `policy` lo prohíbe. Aquí el PDF va al computador de quien ya tiene
    acceso legítimo a esa atención —la descarga lo comprueba con
    `verificar_acceso_atencion`— y no sale del perímetro de la institución.
    """
    psico = Servicio.objects.get(codigo="psicologia")
    u_psi, prof_psi = crear_profesional("psicologo_local", psico, psico.seccion)
    atencion = Atencion.objects.create(
        expediente=escenario["exp"],
        servicio=psico,
        profesional=prof_psi,
        fecha_hora=timezone.now(),
    )
    solicitud = _solicitud(atencion, u_psi)
    assert solicitud.pk is not None


@pytest.mark.django_db
def test_psicologia_sigue_bloqueada_para_un_firmador_externo(escenario, settings):
    """El sello sobre el firmador externo no se tocó."""
    settings.FIRMA_PROVIDER = "firmaec"
    settings.FIRMAEC_SERVICIO_URL = "https://x"
    settings.FIRMAEC_SISTEMA = "sibu"
    settings.FIRMAEC_API_KEY = "k"
    settings.FIRMAEC_CALLBACK_API_KEY = "k"

    psico = Servicio.objects.get(codigo="psicologia")
    u_psi, prof_psi = crear_profesional("psicologo_ec", psico, psico.seccion)
    atencion = Atencion.objects.create(
        expediente=escenario["exp"],
        servicio=psico,
        profesional=prof_psi,
        fecha_hora=timezone.now(),
    )
    with pytest.raises(ValidationError, match="no puede enviarse a un firmador fuera"):
        _solicitud(atencion, u_psi)


@pytest.mark.django_db
def test_quien_no_ve_la_atencion_no_descarga_el_documento(escenario):
    """La descarga es la puerta: si se abriera, el sello daría igual."""
    c = Client()
    c.login(username="ajeno", password=CLAVE)
    assert c.get(f"/firma/descargar-original/{escenario['s'].pk}/").status_code == 403


def _archivo(contenido: bytes):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("firmado.pdf", contenido, content_type="application/pdf")
