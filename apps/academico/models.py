"""
Réplica institucional de solo lectura, alimentada por la carga de la ficha
socioeconómica de matrícula (informe, sección 7). En fase 2 esta app se
alimentará del SGA vía `ApiSgaProvider` sin cambios en el resto del sistema.
"""

from django.db import models

from apps.core.models import ModeloBase, PeriodoAcademico


def estamentos_choices():
    """
    Los cuatro estamentos, leídos del único sitio donde viven.

    Es un invocable y no una lista literal para no importar
    `expediente.models` mientras se define este modelo: `expediente` importa a
    su vez `academico.validators`, y una lista copiada aquí sería la segunda
    fuente de verdad que el propio `Persona.TipoVinculo` advierte de no crear.
    """
    from apps.expediente.models import Persona

    return Persona.ESTAMENTOS_CHOICES


class CargaInstitucional(ModeloBase):
    """Registro de cada carga de archivo Excel/CSV (bitácora, sección 7.2)."""

    class Estado(models.TextChoices):
        SUBIDA = "subida", "Subida"
        MAPEADA = "mapeada", "Mapeada"
        VALIDADA = "validada", "Validada"
        APLICADA = "aplicada", "Aplicada"
        RECHAZADA = "rechazada", "Rechazada"

    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.PROTECT, related_name="cargas")
    # A qué estamento pertenece la gente de ESTE archivo. Cada estamento tiene
    # su propia base y sus propias columnas —un docente no trae ciclo ni
    # paralelo—, así que el archivo no puede decir por sí solo a quién
    # describe: lo declara quien carga, y queda registrado en la bitácora
    # junto al hash del archivo. Por defecto estudiante, que es la carga que
    # ya existía y la única que había antes de este campo.
    estamento = models.CharField(max_length=20, choices=estamentos_choices, default="estudiante")
    nombre_archivo = models.CharField(max_length=255)
    hash_archivo = models.CharField(max_length=64, help_text="SHA-256 del archivo cargado.")
    formato = models.CharField(max_length=8, choices=[("xlsx", "xlsx"), ("csv", "csv")])
    total_filas = models.PositiveIntegerField(default=0)
    altas = models.PositiveIntegerField(default=0)
    actualizaciones = models.PositiveIntegerField(default=0)
    errores = models.PositiveIntegerField(default=0)
    mapeo_columnas = models.JSONField(default=dict, blank=True)
    bitacora = models.JSONField(default=dict, blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.SUBIDA)

    class Meta:
        verbose_name = "carga institucional"
        verbose_name_plural = "cargas institucionales"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Carga {self.periodo} — {self.get_estamento_display()} — {self.nombre_archivo}"


class DatoAcademico(models.Model):
    """
    Fila institucional por persona y período. `ficha_raw` conserva la fila
    original completa (~170 columnas) para trazabilidad y explotación futura.
    Es de solo lectura para el resto del sistema.
    """

    persona = models.ForeignKey(
        "expediente.Persona", on_delete=models.CASCADE, related_name="datos_academicos"
    )
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.PROTECT)
    carga = models.ForeignKey(CargaInstitucional, on_delete=models.SET_NULL, null=True)

    facultad = models.CharField(max_length=150, blank=True)
    carrera = models.CharField(max_length=150, blank=True)
    nivel = models.CharField(max_length=50, blank=True)
    modalidad = models.CharField(max_length=50, blank=True)
    ciclo = models.CharField(max_length=50, blank=True)
    oferta_academica = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=50, blank=True)
    paralelo = models.CharField(max_length=20, blank=True)
    jornada = models.CharField(max_length=50, blank=True)
    email_institucional = models.EmailField(blank=True)

    ficha_raw = models.JSONField(default=dict, help_text="Fila original completa de la ficha.")
    cargado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "dato académico"
        verbose_name_plural = "datos académicos"
        constraints = [
            models.UniqueConstraint(fields=["persona", "periodo"], name="uniq_persona_periodo")
        ]
        indexes = [models.Index(fields=["facultad", "carrera"])]

    def __str__(self):
        return f"{self.persona} @ {self.periodo}"
