"""
Fichas y sesiones de Psicología (informe 6.6).

CONFIDENCIALIDAD: el contenido de este módulo está sellado por RBAC
(`apps.usuarios.rbac.SERVICIOS_CONFIDENCIALES`). Solo el equipo del servicio de
Psicología accede; ni Dirección, ni Coordinación, ni break-the-glass.
Ver apps/usuarios/tests/test_sello_psicologia.py.

El protocolo de riesgo alto notifica al coordinador SIN exponer contenido
clínico: solo le dice que existe un caso y que contacte al servicio.
"""

from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion
from apps.usuarios.models import PerfilProfesional


class FichaPsicologica(models.Model):
    """Ficha de apertura del proceso psicológico."""

    class Riesgo(models.TextChoices):
        BAJO = "bajo", "Bajo"
        MEDIO = "medio", "Medio"
        ALTO = "alto", "Alto"

    class Modalidad(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        VIRTUAL = "virtual", "Virtual"

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Proceso activo"
        ALTA = "alta", "Alta"
        ABANDONO = "abandono", "Abandono"
        DERIVADO = "derivado", "Derivado a externo"

    atencion = models.OneToOneField(
        Atencion, on_delete=models.CASCADE, primary_key=True, related_name="psicologia"
    )
    motivo = models.TextField(blank=True)
    historia_problema = models.TextField(blank=True)
    estado_mental = models.JSONField(
        default=dict, blank=True, help_text="Examen mental: {area: hallazgo}"
    )
    impresion_diagnostica = models.CharField(max_length=255, blank=True)
    plan_terapeutico = models.TextField(blank=True)
    riesgo_nivel = models.CharField(
        max_length=10,
        choices=Riesgo.choices,
        default=Riesgo.BAJO,
        help_text="Riesgo alto dispara protocolo de alerta al coordinador (sin contenido).",
    )
    nota_riesgo = models.TextField(
        blank=True, help_text="Sustento clínico del riesgo. No sale del servicio."
    )
    modalidad = models.CharField(
        max_length=12, choices=Modalidad.choices, default=Modalidad.PRESENCIAL
    )
    estado_proceso = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)

    class Meta:
        verbose_name = "ficha psicológica"
        verbose_name_plural = "fichas psicológicas"

    def __str__(self):
        return f"Ficha psicológica: {self.atencion}"


class SesionPsicologica(models.Model):
    """Sesión del proceso, numerada automáticamente dentro de la ficha."""

    ficha = models.ForeignKey(FichaPsicologica, on_delete=models.CASCADE, related_name="sesiones")
    numero = models.PositiveSmallIntegerField()
    fecha = models.DateField()
    profesional = models.ForeignKey(
        PerfilProfesional,
        on_delete=models.PROTECT,
        related_name="sesiones_psico",
        null=True,
        blank=True,
    )
    temas = models.TextField(blank=True)
    tecnicas = models.CharField(max_length=255, blank=True)
    evolucion = models.TextField(blank=True)
    tareas = models.TextField(blank=True)
    proxima_sesion = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "sesión psicológica"
        verbose_name_plural = "sesiones psicológicas"
        ordering = ["numero"]
        constraints = [
            models.UniqueConstraint(fields=["ficha", "numero"], name="uniq_sesion_por_ficha")
        ]

    def __str__(self):
        return f"Sesión {self.numero} — {self.fecha:%d/%m/%Y}"


class EscalaPsicometrica(ModeloBase):
    """
    Catálogo de escalas aplicables (PHQ-9, GAD-7, Beck…).

    Los tramos se guardan como lista para que el área los mantenga sin código:
        [{"min": 0, "max": 4, "etiqueta": "Mínima", "alerta": false}, ...]
    """

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    puntaje_min = models.PositiveSmallIntegerField(default=0)
    puntaje_max = models.PositiveSmallIntegerField()
    tramos = models.JSONField(default=list, blank=True, help_text="[{min, max, etiqueta, alerta}]")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "escala psicométrica"
        verbose_name_plural = "escalas psicométricas"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"

    def interpretar(self, puntaje: int) -> dict:
        """Devuelve el tramo que corresponde al puntaje."""
        for tramo in self.tramos:
            if tramo.get("min", 0) <= puntaje <= tramo.get("max", self.puntaje_max):
                return tramo
        return {"etiqueta": "Sin interpretación", "alerta": False}


class AplicacionEscala(models.Model):
    """Aplicación de una escala a un paciente en un momento del proceso."""

    ficha = models.ForeignKey(FichaPsicologica, on_delete=models.CASCADE, related_name="escalas")
    escala_catalogo = models.ForeignKey(
        EscalaPsicometrica,
        on_delete=models.PROTECT,
        related_name="aplicaciones",
        null=True,
        blank=True,
    )
    escala = models.CharField(max_length=120, help_text="Nombre de la escala aplicada")
    puntaje = models.CharField(max_length=40, blank=True)
    interpretacion = models.CharField(max_length=120, blank=True)
    alerta = models.BooleanField(default=False)
    fecha = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "aplicación de escala"
        verbose_name_plural = "aplicaciones de escalas"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.escala}: {self.puntaje} ({self.interpretacion})"
