"""
Órdenes y resultados de laboratorio (informe 6.4, 12.4).

Flujo: creada → muestra_tomada → en_proceso → resultado_registrado →
validado → publicado. La validación es en dos pasos (técnico registra,
responsable valida) y al publicar se envía el informe al correo
institucional del paciente.
"""

from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion
from apps.usuarios.models import PerfilProfesional


class Examen(models.Model):
    """Catálogo de exámenes. Cada examen agrupa uno o más parámetros."""

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=150)
    perfil = models.CharField(
        max_length=80, blank=True, help_text="Hematología, Química sanguínea, etc."
    )
    indicaciones_preparacion = models.TextField(
        blank=True, help_text="Ayuno, suspensión de medicación, etc."
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "examen"
        verbose_name_plural = "catálogo de exámenes"
        ordering = ["perfil", "nombre"]

    def __str__(self):
        return self.nombre


class ParametroExamen(models.Model):
    """
    Parámetro medible de un examen, con sus valores de referencia.

    Los rangos pueden diferir por sexo y edad (informe 6.4): se registra un
    parámetro por combinación aplicable y el sistema elige el que corresponde
    al paciente al marcar el resultado.
    """

    class Sexo(models.TextChoices):
        AMBOS = "ambos", "Ambos"
        MASCULINO = "M", "Masculino"
        FEMENINO = "F", "Femenino"

    class TipoValor(models.TextChoices):
        NUMERICO = "numerico", "Numérico"
        CUALITATIVO = "cualitativo", "Cualitativo"
        TEXTO = "texto", "Texto libre"

    examen = models.ForeignKey(Examen, on_delete=models.CASCADE, related_name="parametros")
    nombre = models.CharField(max_length=120)
    unidad = models.CharField(max_length=30, blank=True)
    tipo_valor = models.CharField(
        max_length=12, choices=TipoValor.choices, default=TipoValor.NUMERICO
    )
    orden = models.PositiveSmallIntegerField(default=0)

    # Valores de referencia (solo aplican a tipo numérico)
    sexo = models.CharField(max_length=6, choices=Sexo.choices, default=Sexo.AMBOS)
    edad_min = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Años")
    edad_max = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Años")
    ref_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    ref_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    # Umbrales de valor crítico: fuera de estos rangos se alerta de inmediato
    critico_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    critico_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    class Meta:
        verbose_name = "parámetro de examen"
        verbose_name_plural = "parámetros de exámenes"
        ordering = ["examen", "orden", "nombre"]
        constraints = [
            # Un rango invertido no da error: hace que ningún resultado caiga
            # nunca dentro de la referencia, así que todos salen marcados alto o
            # bajo y la interpretación clínica queda falseada en silencio.
            models.CheckConstraint(
                condition=models.Q(ref_min__isnull=True)
                | models.Q(ref_max__isnull=True)
                | models.Q(ref_min__lte=models.F("ref_max")),
                name="ck_parametro_referencia_coherente",
            ),
            models.CheckConstraint(
                condition=models.Q(critico_min__isnull=True)
                | models.Q(critico_max__isnull=True)
                | models.Q(critico_min__lte=models.F("critico_max")),
                name="ck_parametro_critico_coherente",
            ),
            models.CheckConstraint(
                condition=models.Q(edad_min__isnull=True)
                | models.Q(edad_max__isnull=True)
                | models.Q(edad_min__lte=models.F("edad_max")),
                name="ck_parametro_edad_coherente",
            ),
        ]

    def __str__(self):
        unidad = f" ({self.unidad})" if self.unidad else ""
        return f"{self.nombre}{unidad}"

    def aplica_a(self, sexo: str | None, edad: int | None) -> bool:
        """¿Este rango de referencia aplica al paciente dado?"""
        if self.sexo != self.Sexo.AMBOS and sexo and self.sexo != sexo.upper()[:1]:
            return False
        if edad is not None:
            if self.edad_min is not None and edad < self.edad_min:
                return False
            if self.edad_max is not None and edad > self.edad_max:
                return False
        return True


class OrdenLaboratorio(ModeloBase):
    """Solicitud de exámenes emitida desde Medicina u Odontología."""

    class Estado(models.TextChoices):
        CREADA = "creada", "Creada"
        MUESTRA_TOMADA = "muestra_tomada", "Muestra tomada"
        EN_PROCESO = "en_proceso", "En proceso"
        RESULTADO = "resultado", "Resultado registrado"
        VALIDADO = "validado", "Validado"
        PUBLICADO = "publicado", "Publicado"
        ANULADA = "anulada", "Anulada"
        RECHAZADA = "rechazada", "Muestra rechazada"

    atencion = models.ForeignKey(Atencion, on_delete=models.PROTECT, related_name="ordenes_lab")
    prioridad = models.CharField(
        max_length=10,
        choices=[("rutina", "Rutina"), ("urgente", "Urgente")],
        default="rutina",
    )
    diagnostico_presuntivo = models.CharField(max_length=255, blank=True)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.CREADA)

    # Fase preanalítica
    fecha_toma_muestra = models.DateTimeField(null=True, blank=True)
    responsable_toma = models.ForeignKey(
        PerfilProfesional, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    tipo_muestra = models.CharField(max_length=60, blank=True)
    codigo_barras = models.CharField(max_length=40, blank=True, db_index=True)
    motivo_rechazo = models.CharField(max_length=255, blank=True)

    # Fase postanalítica
    validado_por = models.ForeignKey(
        PerfilProfesional, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    validado_en = models.DateTimeField(null=True, blank=True)
    publicado_en = models.DateTimeField(null=True, blank=True)
    enviado_correo_paciente = models.BooleanField(default=False)

    class Meta:
        verbose_name = "orden de laboratorio"
        verbose_name_plural = "órdenes de laboratorio"
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["estado", "prioridad"])]

    def __str__(self):
        return f"Orden #{self.pk} — {self.get_estado_display()}"

    @property
    def tiene_criticos(self) -> bool:
        return ResultadoParametro.objects.filter(
            orden_examen__orden=self, marcador=ResultadoParametro.Marcador.CRITICO
        ).exists()


class OrdenExamen(models.Model):
    """Examen concreto solicitado dentro de una orden."""

    orden = models.ForeignKey(OrdenLaboratorio, on_delete=models.CASCADE, related_name="examenes")
    examen = models.ForeignKey(Examen, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "examen de la orden"
        verbose_name_plural = "exámenes de la orden"
        constraints = [
            models.UniqueConstraint(fields=["orden", "examen"], name="uniq_orden_examen")
        ]

    def __str__(self):
        return f"{self.examen} (orden #{self.orden_id})"


class ResultadoParametro(models.Model):
    """Valor medido de un parámetro, con su marcador respecto a la referencia."""

    class Marcador(models.TextChoices):
        NORMAL = "normal", "Normal"
        ALTO = "alto", "Alto"
        BAJO = "bajo", "Bajo"
        CRITICO = "critico", "Crítico"

    orden_examen = models.ForeignKey(
        OrdenExamen, on_delete=models.CASCADE, related_name="resultados"
    )
    parametro = models.ForeignKey(
        ParametroExamen, on_delete=models.PROTECT, related_name="resultados"
    )
    valor = models.CharField(max_length=60)
    unidad = models.CharField(max_length=30, blank=True)
    ref_min = models.CharField(max_length=30, blank=True)
    ref_max = models.CharField(max_length=30, blank=True)
    marcador = models.CharField(max_length=10, choices=Marcador.choices, default=Marcador.NORMAL)
    observacion = models.CharField(max_length=255, blank=True)

    registrado_por = models.ForeignKey(
        PerfilProfesional, on_delete=models.PROTECT, related_name="resultados_registrados"
    )
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "resultado de parámetro"
        verbose_name_plural = "resultados de parámetros"
        ordering = ["parametro__orden"]
        constraints = [
            models.UniqueConstraint(
                fields=["orden_examen", "parametro"], name="uniq_resultado_parametro"
            )
        ]

    def __str__(self):
        return f"{self.parametro.nombre}: {self.valor} {self.unidad}".strip()
