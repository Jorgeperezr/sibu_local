"""
Interfaz de proveedor de almacén de evidencias.

Google Drive es *una* implementación, no un supuesto. Mismo patrón que
`AcademicoProvider` y `FirmadorProvider`: el resto del módulo depende solo de
`AlmacenEvidenciasProvider`.

La razón es la de siempre, y ya se pagó dos veces en este proyecto: la
integración externa no está lista (hace falta el OAuth del Workspace
institucional y un Shared Drive), y el sistema tiene que funcionar igual
mientras tanto. Un taller se planifica, se ejecuta y se registran sus
participantes sin que Google exista.

Proveedores (`TALLERES_ALMACEN`):
- `local`  → almacén del propio servidor (por defecto)
- `gdrive` → Google Drive institucional
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from django.conf import settings
from django.core.exceptions import ValidationError


class EvidenciaSubida:
    """Lo que el módulo necesita saber de un archivo ya archivado."""

    def __init__(self, *, file_id: str = "", url: str = "", ruta: str = "", hash_sha256: str = ""):
        self.file_id = file_id
        self.url = url
        self.ruta = ruta
        self.hash_sha256 = hash_sha256


class AlmacenEvidenciasProvider(ABC):
    codigo: str = ""
    nombre: str = ""

    @abstractmethod
    def disponible(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def motivo_no_disponible(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def subir(self, taller, *, nombre: str, contenido: bytes, mime: str) -> EvidenciaSubida:
        raise NotImplementedError


class AlmacenLocalProvider(AlmacenEvidenciasProvider):
    """
    Guarda la evidencia en el almacén del propio servidor.

    Es el defecto: no depende de nadie y las evidencias de un taller
    (fotografías, registro escaneado) no son datos clínicos.
    """

    codigo = "local"
    nombre = "Almacén local"

    def disponible(self) -> bool:
        return bool(getattr(settings, "MEDIA_ROOT", ""))

    def motivo_no_disponible(self) -> str:
        return (
            "MEDIA_ROOT no está configurado: no hay dónde archivar las evidencias. "
            "Defínalo antes de adjuntar archivos."
        )

    def subir(self, taller, *, nombre: str, contenido: bytes, mime: str) -> EvidenciaSubida:
        import os
        from pathlib import Path

        # Sin fallback a /tmp: las evidencias se perderían al reiniciar y
        # quedarían legibles para cualquier usuario del servidor. Es preferible
        # decir que falta configurarlo.
        if not self.disponible():
            raise ValidationError(self.motivo_no_disponible())

        raiz = Path(settings.MEDIA_ROOT) / "talleres" / taller.codigo
        raiz.mkdir(parents=True, exist_ok=True)
        # El nombre lo propone quien sube: se saca cualquier componente de ruta
        # para que no pueda escribir fuera de la carpeta del taller.
        seguro = os.path.basename(nombre).replace("..", "_") or "evidencia"
        destino = raiz / seguro
        destino.write_bytes(contenido)
        return EvidenciaSubida(ruta=str(destino), hash_sha256=hashlib.sha256(contenido).hexdigest())


class GoogleDriveProvider(AlmacenEvidenciasProvider):
    """
    Google Drive institucional.

    Requiere OAuth del Workspace de la UNL y un Shared Drive. Mientras eso no
    exista, `disponible()` es False y el módulo lo dice en vez de fallar.
    """

    codigo = "gdrive"
    nombre = "Google Drive institucional"

    def _faltantes(self) -> list[str]:
        cfg = getattr(settings, "GOOGLE_OAUTH", {})
        faltan = []
        if not cfg.get("CLIENT_SECRETS_FILE"):
            faltan.append("GOOGLE_CLIENT_SECRETS")
        if not cfg.get("SHARED_DRIVE_ID"):
            faltan.append("GOOGLE_SHARED_DRIVE_ID")
        return faltan

    def disponible(self) -> bool:
        return not self._faltantes()

    def motivo_no_disponible(self) -> str:
        return (
            "Google Drive no está configurado en este entorno "
            f"(falta: {', '.join(self._faltantes())}). "
            "Las evidencias pueden archivarse en el almacén local."
        )

    def subir(self, taller, *, nombre: str, contenido: bytes, mime: str) -> EvidenciaSubida:
        if not self.disponible():
            raise ValidationError(self.motivo_no_disponible())
        # La subida real necesita el cliente de Google y las credenciales del
        # Workspace institucional. No se simula: fallar aquí es honesto,
        # inventar un file_id no lo sería.
        raise ValidationError(
            "La subida a Google Drive requiere el cliente de Google Workspace, "
            "que aún no está integrado. Use el almacén local (TALLERES_ALMACEN=local)."
        )


_PROVEEDORES = {
    AlmacenLocalProvider.codigo: AlmacenLocalProvider,
    GoogleDriveProvider.codigo: GoogleDriveProvider,
}


def get_almacen() -> AlmacenEvidenciasProvider:
    codigo = getattr(settings, "TALLERES_ALMACEN", AlmacenLocalProvider.codigo)
    clase = _PROVEEDORES.get(codigo)
    if clase is None:
        raise ValidationError(
            f"TALLERES_ALMACEN='{codigo}' no existe. Opciones: {', '.join(_PROVEEDORES)}."
        )
    return clase()
