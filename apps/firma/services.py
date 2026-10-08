"""
Orquestación de la firma electrónica con FirmaEC.

SIBU: genera el PDF -> pide token -> muestra el enlace -> recibe el firmado.
Todo lo criptográfico ocurre en el equipo del usuario, dentro de FirmaEC.
"""

import base64
import hashlib
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import LogAuditoria

from .models import FirmaDocumento, SolicitudFirma
from .policy import verificar_puede_salir_a_firmar
from .providers import InicioFirma, get_provider

logger = logging.getLogger(__name__)

TAM_MAXIMO_PDF = 15 * 1024 * 1024  # 15 MB


def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def generar_pdf(plantilla: str, contexto: dict) -> bytes:
    """
    Renderiza una plantilla a PDF con el membrete institucional.

    Delega en `apps.core.pdf`, que es donde vive la línea gráfica de la UNL:
    antes este informe salía con tipografía genérica y sin marca, distinto de
    los reportes de gestión.
    """
    from apps.core.pdf import render_pdf

    return render_pdf(plantilla, contexto)


@transaction.atomic
def preparar_solicitud(
    *,
    atencion,
    solicitante,
    pdf: bytes,
    documento_ref_tipo: str,
    documento_ref_id: int,
    tipo_documento: str = "informe",
    razon: str = "",
) -> SolicitudFirma:
    """
    Crea la solicitud a partir de un PDF ya generado.

    No contacta a FirmaEC todavía: primero se comprueba que este contenido
    pueda salir de la institución.
    """
    proveedor = get_provider()
    verificar_puede_salir_a_firmar(atencion, proveedor=proveedor)

    if not pdf:
        raise ValidationError("El documento a firmar está vacío.")
    if len(pdf) > TAM_MAXIMO_PDF:
        raise ValidationError("El documento supera el tamaño máximo admitido (15 MB).")

    # La cédula del firmante vive en la CUENTA (`Usuario.cedula`), no en el
    # perfil profesional. Antes se leía de `solicitante.perfil.cedula`, un campo
    # que no existe: el getattr devolvía "" siempre fuera de las pruebas —que lo
    # tapaban asignando el atributo en memoria— y con FirmaEC la firma no habría
    # arrancado nunca. El firmador local no la usa, así que solo la exige quien
    # la necesita.
    cedula = (getattr(solicitante, "cedula", "") or "").strip()
    if not cedula and proveedor.requiere_cedula_firmante:
        raise ValidationError(
            "Su perfil no tiene cédula registrada. FirmaEC exige la cédula del "
            "firmante para emitir el token."
        )

    # Una sola solicitud abierta por documento: evita tokens paralelos que
    # devolverían firmas duplicadas al mismo registro.
    abierta = SolicitudFirma.objects.filter(
        documento_ref_tipo=documento_ref_tipo,
        documento_ref_id=documento_ref_id,
        estado__in=[SolicitudFirma.Estado.PREPARADA, SolicitudFirma.Estado.ENVIADA],
    ).first()
    if abierta:
        return abierta

    if FirmaDocumento.objects.filter(
        documento_ref_tipo=documento_ref_tipo, documento_ref_id=documento_ref_id
    ).exists():
        raise ValidationError("Este documento ya fue firmado.")

    solicitud = SolicitudFirma.objects.create(
        atencion=atencion,
        documento_ref_tipo=documento_ref_tipo,
        documento_ref_id=documento_ref_id,
        tipo_documento=tipo_documento,
        solicitante=solicitante,
        cedula_solicitante=cedula,
        nombre_documento=f"{tipo_documento}-{documento_ref_id}.pdf",
        pdf_original=pdf,
        hash_original=_sha256(pdf),
        razon=razon,
        creado_por=solicitante,
    )
    return solicitud


def iniciar_firma(solicitud: SolicitudFirma) -> InicioFirma:
    """
    Arranca la firma con el proveedor configurado.

    No sabe qué firmador es: solo pide `iniciar()`. Cambiar de firmador no
    toca esta función.
    """
    if not solicitud.abierta:
        raise ValidationError("Esta solicitud ya no admite firma.")

    proveedor = get_provider()
    if not proveedor.disponible():
        raise ValidationError(proveedor.motivo_no_disponible())
    verificar_puede_salir_a_firmar(solicitud.atencion, proveedor=proveedor)

    inicio = proveedor.iniciar(solicitud)
    solicitud.estado = SolicitudFirma.Estado.ENVIADA
    solicitud.token_expira_en = timezone.now() + timezone.timedelta(minutes=inicio.vigencia_min)
    solicitud.save(update_fields=["estado", "token_expira_en", "actualizado_en"])

    LogAuditoria.objects.create(
        usuario=solicitud.solicitante,
        accion=LogAuditoria.Accion.SIGN_REQUEST,
        modulo="firma",
        entidad="SolicitudFirma",
        entidad_id=str(solicitud.pk),
        expediente_id=solicitud.atencion.expediente_id,
        servicio=solicitud.atencion.servicio.codigo,
        detalle={
            "documento": f"{solicitud.documento_ref_tipo}#{solicitud.documento_ref_id}",
            "hash_original": solicitud.hash_original,
            "proveedor": proveedor.codigo,
        },
    )
    return inicio


def _registrar_rechazo(solicitud: SolicitudFirma, motivo: str) -> None:
    """
    Deja constancia de un intento rechazado, en su propia transacción.

    Tiene que vivir fuera del atomic del asentamiento: si se escribiera dentro,
    el ValidationError que aborta la operación revertiría también este registro
    y los rechazos no dejarían rastro. En una historia clínica, los intentos
    fallidos son justamente los que hay que poder auditar.
    """
    with transaction.atomic():
        SolicitudFirma.objects.filter(pk=solicitud.pk).update(
            estado=SolicitudFirma.Estado.FALLIDA, error=motivo, actualizado_en=timezone.now()
        )
        LogAuditoria.objects.create(
            usuario=solicitud.solicitante,
            accion=LogAuditoria.Accion.SIGN,
            modulo="firma",
            entidad="SolicitudFirma",
            entidad_id=str(solicitud.pk),
            expediente_id=solicitud.atencion.expediente_id,
            servicio=solicitud.atencion.servicio.codigo,
            resultado="rechazado",
            detalle={"motivo": motivo},
        )


def _validar_callback(
    solicitud, cedula, archivo_b64, firmas_validas, integridad, certificado, error
):
    """Devuelve (motivo_de_rechazo, pdf). motivo vacío = todo correcto."""
    # 1. El firmante debe ser quien pidió firmar. Sin esto, cualquier titular de
    #    un certificado válido podría firmar el documento de otro profesional.
    if (cedula or "").strip() != solicitud.cedula_solicitante:
        return "La cédula del firmante no coincide con la de quien solicitó la firma.", None

    # 2. FirmaEC ya validó certificado e integridad: si dice que no, no se guarda.
    if error and error.lower() not in ("null", "none", ""):
        return f"FirmaEC reportó un error: {error}", None
    if not firmas_validas:
        return "FirmaEC reporta que las firmas no son válidas.", None
    if not integridad:
        return "FirmaEC reporta que la firma no cubre todo el documento.", None

    # 3. El contenido debe ser un PDF real y de tamaño razonable.
    try:
        pdf = base64.b64decode(archivo_b64, validate=True)
    except (ValueError, TypeError):
        return "El archivo recibido no es Base64 válido.", None
    if not pdf.startswith(b"%PDF-"):
        return "El archivo recibido no es un PDF.", None
    if len(pdf) > TAM_MAXIMO_PDF:
        return "El documento firmado supera el tamaño máximo admitido.", None

    # 4. Debe traer al menos un certificado; de ahí sale la identidad asentada.
    if not certificado:
        return "El documento firmado no trae información del certificado.", None
    primero = certificado[0]
    if not primero.get("certificadoDigitalValido", False):
        return "El certificado digital no es válido.", None
    if not primero.get("certificadoVigente", True):
        return "El certificado digital no está vigente.", None

    return "", pdf


def recibir_documento_firmado(
    *,
    correlacion: str,
    cedula: str,
    archivo_b64: str,
    firmas_validas: bool,
    integridad_documento: bool,
    certificado: list | None = None,
    error: str = "",
) -> SolicitudFirma:
    """
    Procesa el callback de FirmaEC (`grabar_archivos_firmados`, manual 11.4.2).

    ADVERTENCIA del manual: "Se debe realizar el control previo de los
    documentos recibidos por el servicio web". Este endpoint no lo invoca el
    navegador del usuario sino el servidor de FirmaEC, así que no hay sesión:
    lo único que lo protege es la API Key y estas comprobaciones. Se valida
    todo antes de escribir nada en el expediente.
    """
    solicitud = (
        SolicitudFirma.objects.filter(correlacion=correlacion)
        .select_related("atencion", "solicitante")
        .first()
    )
    if solicitud is None:
        raise ValidationError("No existe una solicitud con esa correlación.")

    # Idempotencia: un reenvío no puede sobrescribir una firma ya asentada, ni
    # reabrir una que ya se cerró.
    if solicitud.estado == SolicitudFirma.Estado.FIRMADA:
        raise ValidationError("Esta solicitud ya fue firmada.")
    if not solicitud.abierta:
        raise ValidationError("Esta solicitud no está abierta.")

    certificado = certificado or []
    motivo, pdf = _validar_callback(
        solicitud, cedula, archivo_b64, firmas_validas, integridad_documento, certificado, error
    )
    if motivo:
        _registrar_rechazo(solicitud, motivo)
        raise ValidationError(motivo)

    return _asentar_firma(solicitud, pdf, certificado)


@transaction.atomic
def _asentar_firma(solicitud: SolicitudFirma, pdf: bytes, certificado: list) -> SolicitudFirma:
    """Escribe la firma. El bloqueo cierra la carrera de dos callbacks a la vez."""
    solicitud = SolicitudFirma.objects.select_for_update().get(pk=solicitud.pk)
    if solicitud.estado == SolicitudFirma.Estado.FIRMADA:
        raise ValidationError("Esta solicitud ya fue firmada.")

    primero = certificado[0]
    solicitud.pdf_firmado = pdf
    solicitud.hash_firmado = _sha256(pdf)
    solicitud.certificado = certificado
    solicitud.estado = SolicitudFirma.Estado.FIRMADA
    solicitud.error = ""
    solicitud.save(
        update_fields=[
            "pdf_firmado",
            "hash_firmado",
            "certificado",
            "estado",
            "error",
            "actualizado_en",
        ]
    )

    FirmaDocumento.objects.create(
        documento_ref_tipo=solicitud.documento_ref_tipo,
        documento_ref_id=solicitud.documento_ref_id,
        usuario=solicitud.solicitante,
        tipo_firma=FirmaDocumento.TipoFirma.DIGITAL,
        hash_documento=solicitud.hash_firmado,
        certificado_serial=primero.get("serial", "")[:120],
        solicitud=solicitud,
        firmante_nombre=primero.get("emitidoPara", "")[:200],
        firmante_cedula=primero.get("cedula", "")[:13],
        entidad_certificadora=primero.get("entidadCertificadora", "")[:120],
        fecha_firma=timezone.now(),
        valida=True,
    )

    LogAuditoria.objects.create(
        usuario=solicitud.solicitante,
        accion=LogAuditoria.Accion.SIGN,
        modulo="firma",
        entidad="SolicitudFirma",
        entidad_id=str(solicitud.pk),
        expediente_id=solicitud.atencion.expediente_id,
        servicio=solicitud.atencion.servicio.codigo,
        resultado="ok",
        detalle={
            "documento": f"{solicitud.documento_ref_tipo}#{solicitud.documento_ref_id}",
            "hash_firmado": solicitud.hash_firmado,
            "firmante": primero.get("emitidoPara", ""),
            "entidad_certificadora": primero.get("entidadCertificadora", ""),
            "serial": primero.get("serial", ""),
        },
    )
    return solicitud


# ============================================================
# Firma en el computador del profesional
# ============================================================

# Un informe clínico firmado son cientos de KB, no megas. El tope corta el
# archivo equivocado antes de cargarlo entero en memoria.
TAMANO_MAXIMO_PDF = 20 * 1024 * 1024


@transaction.atomic
def asentar_firma_subida(solicitud: SolicitudFirma, pdf: bytes, usuario) -> SolicitudFirma:
    """
    Asienta un PDF que el profesional firmó en su computador y volvió a subir.

    SIBU no extrae ni valida el certificado: la criptografía nunca toca el
    servidor. Por eso el registro queda como firma electrónica simple y no como
    digital con certificado —decir lo segundo sería afirmar algo que no se
    comprobó—. Lo que sí se conserva es el hash de lo subido y quién lo subió.

    Subir es opcional: el profesional puede quedarse el documento firmado en su
    equipo. Esto solo cubre el caso de quien decide dejarlo en el expediente.
    """
    if not pdf:
        raise ValidationError("No se recibió ningún archivo.")
    if len(pdf) > TAMANO_MAXIMO_PDF:
        raise ValidationError("El archivo supera el tamaño máximo permitido (20 MB).")
    if not pdf.startswith(b"%PDF-"):
        raise ValidationError("El archivo subido no es un PDF.")

    # El bloqueo cierra la carrera de dos subidas simultáneas de la misma
    # solicitud: sin él, ambas crearían su FirmaDocumento.
    solicitud = SolicitudFirma.objects.select_for_update().get(pk=solicitud.pk)
    if solicitud.estado == SolicitudFirma.Estado.FIRMADA:
        raise ValidationError("Esta solicitud ya tiene un documento firmado.")

    solicitud.pdf_firmado = pdf
    solicitud.hash_firmado = _sha256(pdf)
    solicitud.estado = SolicitudFirma.Estado.FIRMADA
    solicitud.error = ""
    solicitud.save(
        update_fields=["pdf_firmado", "hash_firmado", "estado", "error", "actualizado_en"]
    )

    FirmaDocumento.objects.create(
        documento_ref_tipo=solicitud.documento_ref_tipo,
        documento_ref_id=solicitud.documento_ref_id,
        usuario=usuario,
        tipo_firma=FirmaDocumento.TipoFirma.ELECTRONICA,
        hash_documento=solicitud.hash_firmado,
        solicitud=solicitud,
        firmante_nombre=usuario.get_full_name()[:200],
        fecha_firma=timezone.now(),
        valida=True,
    )

    LogAuditoria.objects.create(
        usuario=usuario,
        accion=LogAuditoria.Accion.SIGN,
        modulo="firma",
        entidad="SolicitudFirma",
        entidad_id=str(solicitud.pk),
        expediente_id=solicitud.atencion.expediente_id,
        servicio=solicitud.atencion.servicio.codigo,
        resultado="ok",
        detalle={
            "documento": f"{solicitud.documento_ref_tipo}#{solicitud.documento_ref_id}",
            "hash_firmado": solicitud.hash_firmado,
            "origen": "subida manual del profesional",
            "certificado_verificado": False,
        },
    )
    return solicitud


def expirar_vencidas() -> int:
    """Cierra las solicitudes cuyo token caducó sin que llegara la firma."""
    vencidas = SolicitudFirma.objects.filter(
        estado=SolicitudFirma.Estado.ENVIADA, token_expira_en__lt=timezone.now()
    )
    return vencidas.update(estado=SolicitudFirma.Estado.EXPIRADA)
