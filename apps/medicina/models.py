"""
Historia clínica médica (informe 6.1).

Formato tipo 002/003/005 del MSP adaptado a la UNL. La atención hereda del
modelo base Atencion (informe 11.3) y extiende con anamnesis, examen físico
y plan. Los diagnósticos se registran en múltiples filas con CIE-10.
"""

from django.db import models

from apps.core.models import CIE10
from apps.expediente.models import Atencion


class AtencionMedicina(models.Model):
    """
    Extensión OneToOne de Atencion para el servicio de Medicina.

    - anamnesis: motivo, enfermedad actual y revisión por sistemas.
    - examen_fisico: JSON con hallazgos por sistemas.
    - plan_tratamiento: indicaciones y seguimiento.
    - Los signos vitales NO se guardan aquí sino en enfermeria.SignosVitales
      (por expediente + fecha_hora), para que sean reutilizables.
    """

    atencion = models.OneToOneField(
        Atencion,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="medicina",
    )

    # Anamnesis
    enfermedad_actual = models.TextField(
        blank=True, help_text="Cronología del padecimiento actual."
    )
    revision_sistemas = models.JSONField(
        default=dict,
        blank=True,
        help_text="{sistema: hallazgos}, ej: {'cardio': 'palpitaciones ocasionales'}",
    )

    # Examen físico
    examen_fisico = models.JSONField(
        default=dict, blank=True, help_text="{region/sistema: hallazgos}"
    )

    # Plan
    plan_tratamiento = models.TextField(blank=True)
    indicaciones = models.TextField(blank=True)
    dias_reposo = models.PositiveSmallIntegerField(null=True, blank=True)
    proxima_cita_sugerida = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "atención de medicina"
        verbose_name_plural = "atenciones de medicina"

    def __str__(self):
        return f"HC médica: {self.atencion}"


class Diagnostico(models.Model):
    """
    Diagnóstico CIE-10 asociado a la atención. Una atención puede tener
    varios diagnósticos; exactamente uno debe marcarse como principal.
    """

    class TipoDx(models.TextChoices):
        PRESUNTIVO = "presuntivo", "Presuntivo"
        DEFINITIVO = "definitivo", "Definitivo"

    class Condicion(models.TextChoices):
        PRIMERA = "primera", "Primera vez"
        SUBSECUENTE = "subsecuente", "Subsecuente"

    atencion = models.ForeignKey(Atencion, on_delete=models.CASCADE, related_name="diagnosticos")
    cie10 = models.ForeignKey(CIE10, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=12, choices=TipoDx.choices, default=TipoDx.PRESUNTIVO)
    condicion = models.CharField(
        max_length=12, choices=Condicion.choices, default=Condicion.PRIMERA
    )
    principal = models.BooleanField(default=False)
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "diagnóstico"
        verbose_name_plural = "diagnósticos"
        indexes = [models.Index(fields=["atencion", "principal"])]
        constraints = [
            models.UniqueConstraint(
                fields=["atencion", "cie10"],
                name="uniq_atencion_cie10",
            ),
        ]

    def __str__(self):
        marca = " ⭐" if self.principal else ""
        return f"{self.cie10.codigo} ({self.get_tipo_display()}){marca}"
