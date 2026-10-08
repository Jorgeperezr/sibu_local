"""
Endpoint de retorno de FirmaEC.

El manual (11.4.2) obliga a que la acción se llame `grabar_archivos_firmados`,
consuma application/json y responda texto plano "OK".

Quién llama aquí NO es el navegador del usuario: es el servidor de FirmaEC.
Por tanto no hay sesión ni CSRF, y la única credencial es la API Key. Todo lo
demás lo sostienen las validaciones de services.recibir_documento_firmado().
"""

import hmac
import json
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services

logger = logging.getLogger(__name__)

PREFIJO = "SIBU-"
SUFIJO = ".pdf"


def _api_key_valida(request) -> bool:
    """Compara en tiempo constante: una comparación normal filtra la clave."""
    esperada = getattr(settings, "FIRMAEC_CALLBACK_API_KEY", "")
    recibida = request.headers.get("X-API-KEY", "")
    if not esperada:
        logger.error("FIRMAEC_CALLBACK_API_KEY sin configurar: se rechaza el callback.")
        return False
    return hmac.compare_digest(esperada, recibida)


def _extraer_correlacion(nombre: str) -> str:
    """
    Recupera la correlación del nombre del archivo.

    Es el único punto de anclaje: el callback no trae un id nuestro.
    """
    nombre = (nombre or "").strip()
    if not nombre.startswith(PREFIJO) or not nombre.endswith(SUFIJO):
        return ""
    return nombre[len(PREFIJO) : -len(SUFIJO)]


@csrf_exempt
@require_POST
def grabar_archivos_firmados(request):
    """Recibe el PDF firmado desde FirmaEC."""
    # Si el firmador configurado no es FirmaEC, este endpoint no debe existir
    # operativamente: no se acepta un retorno de un firmador que no usamos.
    from .providers import FirmaECProvider, get_provider

    if get_provider().codigo != FirmaECProvider.codigo:
        return HttpResponse("Firmador no habilitado", status=404, content_type="text/plain")

    if not _api_key_valida(request):
        logger.warning(
            "Callback de FirmaEC con API Key inválida desde %s", request.META.get("REMOTE_ADDR")
        )
        return HttpResponse("API Key inválida", status=403, content_type="text/plain")

    try:
        datos = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("JSON inválido", status=400, content_type="text/plain")

    correlacion = _extraer_correlacion(datos.get("nombreDocumento", ""))
    if not correlacion:
        logger.warning("Callback de FirmaEC con nombreDocumento no reconocible.")
        return HttpResponse("Documento no reconocido", status=400, content_type="text/plain")

    try:
        services.recibir_documento_firmado(
            correlacion=correlacion,
            cedula=datos.get("cedula", ""),
            archivo_b64=datos.get("archivo", ""),
            firmas_validas=bool(datos.get("firmasValidas", False)),
            integridad_documento=bool(datos.get("integridadDocumento", False)),
            certificado=datos.get("certificado", []),
            error=str(datos.get("error", "") or ""),
        )
    except ValidationError as exc:
        logger.warning("Callback de FirmaEC rechazado: %s", exc.messages)
        return HttpResponse(" ".join(exc.messages), status=400, content_type="text/plain")

    # El manual espera exactamente "OK".
    return HttpResponse("OK", content_type="text/plain")


def estado_solicitud(request, pk):
    """
    Consultado por el navegador mientras el usuario firma en FirmaEC.

    El firmador no puede avisar a la pestaña, así que la pantalla pregunta.
    """
    from apps.usuarios.decorators import verificar_acceso_atencion

    from .models import SolicitudFirma

    solicitud = SolicitudFirma.objects.select_related("atencion").filter(pk=pk).first()
    if solicitud is None:
        return JsonResponse({"detail": "No encontrada."}, status=404)
    verificar_acceso_atencion(request.user, solicitud.atencion)
    return JsonResponse(
        {
            "estado": solicitud.estado,
            "firmada": solicitud.estado == SolicitudFirma.Estado.FIRMADA,
            "error": solicitud.error,
        }
    )
