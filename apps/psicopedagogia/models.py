"""Ficha psicopedagógica y plan de intervención (informe 6.7)."""

from django.db import models

from apps.expediente.models import Atencion


class FichaPsicopedagogica(models.Model):
    atencion = models.OneToOneField(
        Atencion, on_delete=models.CASCADE, primary_key=True, related_name="psicopedagogia"
    )
    motivo = models.CharField(max_length=255, blank=True)
    historial_academico = models.JSONField(default=dict, blank=True)
    estilos_aprendizaje = models.JSONField(default=dict, blank=True)
    plan_intervencion = models.TextField(blank=True)

    class Meta:
        verbose_name = "ficha psicopedagógica"
        verbose_name_plural = "fichas psicopedagógicas"

    def __str__(self):
        return f"Ficha psicopedagógica: {self.atencion}"


class SeguimientoAcademico(models.Model):
    ficha = models.ForeignKey(
        FichaPsicopedagogica, on_delete=models.CASCADE, related_name="seguimientos"
    )
    periodo = models.CharField(max_length=20)
    promedio_antes = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    promedio_despues = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    observaciones = models.TextField(blank=True)

    def __str__(self):
        return f"Seguimiento {self.periodo} — {self.ficha}"
