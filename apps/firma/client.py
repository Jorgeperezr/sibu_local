"""
Cliente HTTP del servicio FirmaEC (proyecto `firmadigital-servicio`).

Única pieza que habla con el exterior. No hace criptografía: envía el PDF y
recibe un JWT de corta vida (5 minutos por defecto) que habilita al firmador
de escritorio.

Manual de Implementación FirmaEC Descentralizada 2.1.0, sección 12.1.
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError

logger = logging.getLogger(__name__)

TIMEOUT = 20


class ErrorFirmaEC(ValidationError):
    """El servicio FirmaEC no pudo crear el documento."""


def _config(clave, defecto=None, obligatorio=True):
    valor = getattr(settings, clave, defecto)
    if obligatorio and not valor:
        raise ImproperlyConfigured(
            f"Falta {clave}. Configure la integración con FirmaEC antes de usarla."
        )
    return valor


def _url_servicio() -> str:
    """
    Valida el esquema antes de abrir la URL.

    urlopen acepta file:// y otros esquemas: una URL mal configurada podría
    leer el disco del servidor en lugar de hablar con FirmaEC. Se exige https,
    salvo localhost para desarrollo.
    """
    url = _config("FIRMAEC_SERVICIO_URL").rstrip("/") + "/documentos"
    partes = urllib.parse.urlparse(url)
    if partes.scheme == "http" and partes.hostname in ("localhost", "127.0.0.1"):
        return url
    if partes.scheme != "https":
        raise ImproperlyConfigured(
            f"FIRMAEC_SERVICIO_URL debe usar https (recibido: '{partes.scheme}')."
        )
    return url


def crear_documento(*, cedula: str, nombre: str, pdf: bytes) -> str:
    """
    POST /servicio/documentos -> devuelve el JWT.

    El JWT lleva {cedula, sistema, ids, exp} y es lo único que el firmador
    necesita para recuperar el documento. No contiene el PDF.
    """
    url = _url_servicio()
    cuerpo = json.dumps(
        {
            "sistema": _config("FIRMAEC_SISTEMA"),
            "cedula": cedula,
            "documentos": [{"nombre": nombre, "documento": base64.b64encode(pdf).decode("ascii")}],
        }
    ).encode("utf-8")

    peticion = urllib.request.Request(  # noqa: S310 - esquema validado en _url_servicio
        url,
        data=cuerpo,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-KEY": _config("FIRMAEC_API_KEY"),
        },
    )
    try:
        # El esquema ya está restringido a https/localhost en _url_servicio().
        with urllib.request.urlopen(peticion, timeout=TIMEOUT) as respuesta:  # noqa: S310  # nosec B310
            token = respuesta.read().decode("utf-8").strip()
    except urllib.error.HTTPError as exc:
        detalle = {403: "API Key rechazada por FirmaEC.", 400: "FirmaEC rechazó el JSON."}
        logger.warning("FirmaEC HTTP %s al crear documento", exc.code)
        raise ErrorFirmaEC(detalle.get(exc.code, f"FirmaEC respondió HTTP {exc.code}.")) from exc
    except urllib.error.URLError as exc:
        logger.warning("FirmaEC inalcanzable: %s", exc.reason)
        raise ErrorFirmaEC("No se pudo contactar al servicio FirmaEC.") from exc

    if not token or token.count(".") != 2:
        raise ErrorFirmaEC("FirmaEC no devolvió un JWT válido.")
    return token


def construir_enlace(token: str, *, razon: str = "", tipo_certificado: int = 2) -> str:
    """
    Arma el enlace `firmaec://` que dispara el firmador de escritorio.

    Manual 12.3: firmaec://sistema/accion?parametros, codificados según RFC 3986.
    El navegador entrega este enlace al Protocol Handler que registra el
    instalador de FirmaEC en el sistema operativo del usuario.

    tipo_certificado: 1=Token USB, 2=Archivo .p12, 3=Tarjeta inteligente (cédula).
    """
    sistema = _config("FIRMAEC_SISTEMA")
    parametros = {
        "token": token,
        "tipo_certificado": tipo_certificado,
        # Estampado visible: FirmaEC no marca el PDF salvo que se le pida.
        "estampado": "QR",
        "llx": 30,
        "lly": 40,
        "razon": (razon or _config("FIRMAEC_RAZON", "Firma de responsabilidad", False))[:70],
    }
    if _config("FIRMAEC_PREPRODUCCION", False, obligatorio=False):
        parametros["pre"] = "true"
    consulta = urllib.parse.urlencode(parametros, quote_via=urllib.parse.quote)
    return f"firmaec://{urllib.parse.quote(sistema)}/firmar?{consulta}"
