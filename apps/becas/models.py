"""
Becas — alcance fase 1 (informe 6.9): registro/visualización de beneficiarios
y seguimiento por período. El ciclo convocatoria→adjudicación se integrará con
el sistema institucional existente en fase 2 (campo `id_externo`).
"""

from django.db import models

from apps.core.models import ModeloBase, PeriodoAcademico
from apps.expediente.models import Expediente
from apps.usuarios.models import PerfilProfesional


class TipoBeca(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo = models.SlugField(max_length=30, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "tipo de beca"
        verbose_name_plural = "tipos de beca"

    def __str__(self):
        return self.nombre


class BecaBeneficiario(ModeloBase):
    class Origen(models.TextChoices):
        MANUAL = "manual", "Registro manual"
        CARGA = "carga_masiva", "Carga masiva"
        API = "api_externa", "API sistema de becas"

    class Estado(models.TextChoices):
        REGISTRADO = "registrado", "Registrado"
        EN_SEGUIMIENTO = "en_seguimiento", "En seguimiento"
        SUSPENDIDO = "suspendido", "Suspendido"
        TERMINADO = "terminado", "Terminado"

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="becas")
    tipo_beca = models.ForeignKey(TipoBeca, on_delete=models.PROTECT)
    periodo_desde = models.ForeignKey(
        PeriodoAcademico, on_delete=models.PROTECT, related_name="becas_desde"
    )
    periodo_hasta = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="becas_hasta",
    )
    monto_o_porcentaje = models.CharField(max_length=60, blank=True)
    resolucion = models.CharField(max_length=120, blank=True)
    # Datos bancarios cifrados a nivel de aplicación (informe 7.3, 14.4)
    datos_bancarios_cifrados = models.JSONField(default=dict, blank=True)
    origen = models.CharField(max_length=14, choices=Origen.choices, default=Origen.MANUAL)
    id_externo = models.CharField(
        max_length=60, blank=True, help_text="Clave en el sistema de becas institucional (fase 2)."
    )
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.REGISTRADO)
    causal = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "beneficiario de beca"
        verbose_name_plural = "beneficiarios de becas"

    def __str__(self):
        return f"{self.expediente.persona} — {self.tipo_beca}"


class SeguimientoBeca(models.Model):
    class Tipo(models.TextChoices):
        ENTREVISTA = "entrevista", "Entrevista"
        VERIFICACION = "verificacion_matricula", "Verificación de matrícula"
        NOVEDAD = "novedad", "Novedad"
        INFORME_SOCIAL = "informe_social", "Informe social"

    beneficiario = models.ForeignKey(
        BecaBeneficiario, on_delete=models.CASCADE, related_name="seguimientos"
    )
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.PROTECT)
    fecha = models.DateField(auto_now_add=True)
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    detalle = models.TextField(blank=True)
    matricula_vigente = models.BooleanField(null=True, blank=True)
    registrado_por = models.ForeignKey(PerfilProfesional, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "seguimiento de beca"
        verbose_name_plural = "seguimientos de becas"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.beneficiario} ({self.periodo})"
