"""Reportes generados y su programación (informe 5.2 M20, sección 15)."""

from django.db import models

from apps.core.models import ModeloBase


class ReporteGenerado(ModeloBase):
    class Periodicidad(models.TextChoices):
        MENSUAL = "mensual", "Mensual"
        SEMESTRAL = "semestral", "Semestral"
        ANUAL = "anual", "Anual"
        A_DEMANDA = "a_demanda", "A demanda"

    nombre = models.CharField(max_length=150)
    periodicidad = models.CharField(max_length=12, choices=Periodicidad.choices)
    parametros = models.JSONField(default=dict, blank=True)
    archivo_documento = models.ForeignKey(
        "documentos.DocumentoAnexo", null=True, blank=True, on_delete=models.SET_NULL
    )
    generado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "reporte generado"
        verbose_name_plural = "reportes generados"
        ordering = ["-generado_en"]
