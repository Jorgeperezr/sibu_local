"""
Interfaz de proveedor de datos institucionales.

Fase 1: `CargaArchivoProvider` (lee de la réplica alimentada por Excel/CSV).
Fase 2: `ApiSgaProvider` (consulta el SGA por API/vistas). El resto del
sistema solo depende de `AcademicoProvider.consultar_persona`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AcademicoProvider(ABC):
    @abstractmethod
    def consultar_persona(self, cedula: str) -> dict | None:
        """Devuelve datos institucionales de la persona o None si no existe."""
        raise NotImplementedError


class CargaArchivoProvider(AcademicoProvider):
    """Fase 1: consulta la réplica cargada desde la ficha socioeconómica."""

    def consultar_persona(self, cedula: str) -> dict | None:
        from apps.expediente.models import Persona

        persona = Persona.objects.filter(cedula=cedula).prefetch_related("datos_academicos").first()
        if persona is None:
            return None
        dato = persona.datos_academicos.order_by("-periodo__fecha_inicio").first()
        return {
            "cedula": persona.cedula,
            "nombres": persona.nombres,
            "apellidos": persona.apellidos,
            "tipo_vinculo": persona.tipo_vinculo,
            "facultad": getattr(dato, "facultad", ""),
            "carrera": getattr(dato, "carrera", ""),
            "ciclo": getattr(dato, "ciclo", ""),
            "modalidad": getattr(dato, "modalidad", ""),
            "jornada": getattr(dato, "jornada", ""),
            "estado": getattr(dato, "estado", ""),
            "email_institucional": getattr(dato, "email_institucional", ""),
            "periodo": getattr(getattr(dato, "periodo", None), "codigo", ""),
        }


class ApiSgaProvider(AcademicoProvider):  # pragma: no cover - fase 2
    """Fase 2: integración directa con el SGA. Pendiente de implementación."""

    def consultar_persona(self, cedula: str) -> dict | None:
        raise NotImplementedError("Integración con el SGA prevista para la fase 2.")


def get_provider() -> AcademicoProvider:
    """Punto único de obtención del proveedor activo (configurable en fase 2)."""
    return CargaArchivoProvider()
