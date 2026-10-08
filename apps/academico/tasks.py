"""Tareas asíncronas del módulo académico (cargas grandes sin bloquear la UI)."""

from celery import shared_task

from .models import CargaInstitucional
from .services import LectorFicha, ProcesadorCarga


@shared_task
def aplicar_carga_async(carga_id: int, ruta: str):
    """Aplica una carga previamente subida y validada. Devuelve el resumen."""
    carga = CargaInstitucional.objects.get(pk=carga_id)
    formato = carga.formato
    lector = LectorFicha(ruta, formato)
    resultado = ProcesadorCarga(carga, carga.mapeo_columnas).procesar(lector, aplicar=True)
    carga.total_filas = resultado.total
    carga.altas = resultado.altas
    carga.actualizaciones = resultado.actualizaciones
    carga.errores = resultado.errores
    carga.estado = CargaInstitucional.Estado.APLICADA
    carga.bitacora = resultado.as_dict()
    carga.save()
    return resultado.as_dict()
