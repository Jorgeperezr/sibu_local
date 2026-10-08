"""
Interfaz de proveedor de firma.

FirmaEC es *una* implementación, no un supuesto del sistema. El resto de SIBU
depende solo de `FirmadorProvider`: cambiar de firmador —o quedarse sin
ninguno— no debe tocar servicios, vistas ni plantillas.

Esto importa por dos razones concretas:

1. **FirmaEC no está disponible todavía.** Exige registro ante el MINTEL y un
   AIF delegado por oficio. Hasta que eso ocurra, el sistema tiene que arrancar
   y funcionar igual, con la firma apagada y diciéndolo claramente — no
   reventando con un ImproperlyConfigured en medio de una consulta.

2. **El firmador puede cambiar.** El Acuerdo Ministerial 017-2020 permite a una
   institución usar otro sistema si es compatible con los certificados
   acreditados por ARCOTEL. Si mañana la UNL adopta otro, el punto de cambio es
   este archivo.

Proveedores disponibles (`FIRMA_PROVIDER`):
- `firmaec`        → FirmaEC del MINTEL (protocolo firmaec:// + callback REST)
- `deshabilitada`  → sin firma; el sistema lo dice y sigue funcionando
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from django.conf import settings
from django.core.exceptions import ValidationError


class InicioFirma:
    """
    Lo que un firmador necesita devolver para que la interfaz actúe.

    `tipo` describe *cómo* se invoca al firmador, no quién es:
    - "enlace": el navegador abre una URL (protocolo propio del SO).
    Un firmador futuro podría devolver otro tipo sin cambiar el modelo.
    """

    def __init__(self, tipo: str, enlace: str = "", vigencia_min: int = 5, ayuda: str = ""):
        self.tipo = tipo
        self.enlace = enlace
        self.vigencia_min = vigencia_min
        self.ayuda = ayuda


class FirmadorProvider(ABC):
    codigo: str = ""
    nombre: str = ""
    # Si el firmador saca el documento fuera de la institución. Determina si
    # puede tocar contenido confidencial (ver policy.py).
    externo: bool = True
    # Si necesita la cédula del firmante para arrancar. Es un requisito de
    # FirmaEC —el callback correlaciona por cédula—, no del acto de firmar: un
    # firmador que no la use no debe bloquear la generación del documento.
    requiere_cedula_firmante: bool = False

    @abstractmethod
    def disponible(self) -> bool:
        """¿Está configurado y utilizable ahora mismo?"""
        raise NotImplementedError

    @abstractmethod
    def motivo_no_disponible(self) -> str:
        """Qué decirle al usuario si no lo está. En su idioma, no un stacktrace."""
        raise NotImplementedError

    @abstractmethod
    def nombre_archivo(self, solicitud) -> str:
        """Nombre con el que el documento viaja al firmador y vuelve."""
        raise NotImplementedError

    @abstractmethod
    def iniciar(self, solicitud) -> InicioFirma:
        """Arranca la firma y devuelve lo que la interfaz debe presentar."""
        raise NotImplementedError


class FirmaECProvider(FirmadorProvider):
    """FirmaEC (MINTEL): protocolo firmaec:// + callback grabar_archivos_firmados."""

    codigo = "firmaec"
    nombre = "FirmaEC (MINTEL)"
    externo = True
    requiere_cedula_firmante = True

    _REQUERIDOS = (
        "FIRMAEC_SERVICIO_URL",
        "FIRMAEC_SISTEMA",
        "FIRMAEC_API_KEY",
        "FIRMAEC_CALLBACK_API_KEY",
    )

    def _faltantes(self) -> list[str]:
        return [c for c in self._REQUERIDOS if not getattr(settings, c, "")]

    def disponible(self) -> bool:
        return not self._faltantes()

    def motivo_no_disponible(self) -> str:
        faltan = ", ".join(self._faltantes())
        return (
            "La firma electrónica no está configurada en este entorno "
            f"(falta: {faltan}). Requiere el registro de SIBU ante el MINTEL."
        )

    def nombre_archivo(self, solicitud) -> str:
        # La correlación viaja aquí: es el único campo que el callback devuelve.
        return f"SIBU-{solicitud.correlacion}.pdf"

    def iniciar(self, solicitud) -> InicioFirma:
        from . import client

        token = client.crear_documento(
            cedula=solicitud.cedula_solicitante,
            nombre=self.nombre_archivo(solicitud),
            pdf=bytes(solicitud.pdf_original),
        )
        return InicioFirma(
            tipo="enlace",
            enlace=client.construir_enlace(token, razon=solicitud.razon),
            vigencia_min=5,
            ayuda=(
                "Se abrirá FirmaEC en su computador. Si no ocurre nada, instálelo "
                "desde https://www.firmadigital.gob.ec/descargar-firmaec/"
            ),
        )


class FirmaLocalProvider(FirmadorProvider):
    """
    El profesional firma en su propio computador.

    SIBU genera el PDF y se lo entrega; el profesional lo firma con su
    certificado y el software que ya use, y decide si vuelve a subirlo al
    expediente o se lo queda. La criptografía nunca toca el servidor y el
    documento no viaja a ningún servicio de terceros.

    `externo = False` no es un detalle: el documento no sale del perímetro de la
    institución, va al equipo de quien ya tiene acceso legítimo a esa atención
    —la descarga lo comprueba—. Por eso `policy.verificar_puede_salir_a_firmar`
    lo deja pasar también en Psicología, cosa que con FirmaEC no ocurre.
    """

    codigo = "local"
    nombre = "Firma en el computador del profesional"
    externo = False

    def disponible(self) -> bool:
        # No depende de ningún servicio externo ni de credenciales: si el
        # sistema levanta, esto funciona.
        return True

    def motivo_no_disponible(self) -> str:
        return ""

    def nombre_archivo(self, solicitud) -> str:
        return solicitud.nombre_documento

    def iniciar(self, solicitud) -> InicioFirma:
        from django.urls import reverse

        return InicioFirma(
            tipo="descarga",
            enlace=reverse("firma:descargar_original", args=[solicitud.pk]),
            vigencia_min=0,
            ayuda=(
                "Descargue el documento y fírmelo en su computador con su certificado. "
                "Si quiere dejarlo asentado en el expediente, vuelva a esta pantalla y "
                "súbalo firmado."
            ),
        )


class FirmaDeshabilitadaProvider(FirmadorProvider):
    """
    Sin firmador. No es un error: es un estado legítimo del despliegue.

    Deja que todo lo demás del sistema funcione mientras la firma no esté
    disponible, en vez de convertir su ausencia en una excepción a mitad de una
    consulta clínica.
    """

    codigo = "deshabilitada"
    nombre = "Firma electrónica no habilitada"
    externo = False

    def disponible(self) -> bool:
        return False

    def motivo_no_disponible(self) -> str:
        return (
            "La firma electrónica no está habilitada en esta instalación. "
            "Los documentos pueden generarse y descargarse, pero no firmarse."
        )

    def nombre_archivo(self, solicitud) -> str:
        return solicitud.nombre_documento

    def iniciar(self, solicitud) -> InicioFirma:
        raise ValidationError(self.motivo_no_disponible())


_PROVEEDORES = {
    FirmaLocalProvider.codigo: FirmaLocalProvider,
    FirmaECProvider.codigo: FirmaECProvider,
    FirmaDeshabilitadaProvider.codigo: FirmaDeshabilitadaProvider,
}


def get_provider() -> FirmadorProvider:
    """
    Devuelve el firmador configurado.

    Por defecto, el local: el profesional descarga el PDF y lo firma en su
    computador. FirmaEC sigue implementado y se elige poniendo
    FIRMA_PROVIDER="firmaec", pero requiere el registro de SIBU ante el MINTEL.
    """
    codigo = getattr(settings, "FIRMA_PROVIDER", FirmaLocalProvider.codigo)
    clase = _PROVEEDORES.get(codigo)
    if clase is None:
        raise ValidationError(
            f"FIRMA_PROVIDER='{codigo}' no existe. Opciones: {', '.join(_PROVEEDORES)}."
        )
    return clase()
