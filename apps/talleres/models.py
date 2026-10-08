"""
Talleres y actividades grupales (informe 5.2 M21, 6.10).

Disponible para Psicopedagogía y Trabajo Social; habilitable para Salud por
parámetro del Administrador (`Servicio.permite_talleres`). Las evidencias
(fotografías y registro escaneado PDF) se archivan en el Google Drive
institucional del responsable; en la BD se guarda file_id + enlace + hash.
"""

from django.db import models

from apps.core.models import ModeloBase, Seccion, Servicio
from apps.expediente.models import Expediente
from apps.usuarios.models import PerfilProfesional


class Taller(ModeloBase):
    class Tipo(models.TextChoices):
        PREVENTIVO = "preventivo", "Preventivo"
        PROMOCIONAL = "promocional", "Promocional"
        FORMATIVO = "formativo", "Formativo"

    class Estado(models.TextChoices):
        PLANIFICADO = "planificado", "Planificado"
        EJECUTADO = "ejecutado", "Ejecutado"
        DOCUMENTADO = "documentado", "Documentado"
        CERRADO = "cerrado", "Cerrado"

    codigo = models.CharField(max_length=30, unique=True)
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name="talleres")
    seccion = models.ForeignKey(Seccion, on_delete=models.PROTECT)
    tema = models.CharField(max_length=200)
    objetivo = models.TextField(blank=True)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.PREVENTIVO)
    responsable = models.ForeignKey(
        PerfilProfesional, on_delete=models.PROTECT, related_name="talleres"
    )
    cofacilitadores = models.JSONField(default=list, blank=True)
    fecha = models.DateField()
    hora_inicio = models.TimeField(null=True, blank=True)
    duracion_min = models.PositiveSmallIntegerField(null=True, blank=True)
    modalidad = models.CharField(
        max_length=12,
        choices=[("presencial", "Presencial"), ("virtual", "Virtual")],
        default="presencial",
    )
    lugar = models.CharField(max_length=200, blank=True)
    poblacion_objetivo = models.JSONField(default=dict, blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PLANIFICADO)
    gdrive_folder_id = models.CharField(max_length=120, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "taller"
        verbose_name_plural = "talleres"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.codigo} — {self.tema}"

    @property
    def total_participantes(self):
        return self.participantes.count()


class TallerParticipante(models.Model):
    class Origen(models.TextChoices):
        LISTA = "seleccion_lista", "Selección de lista"
        CEDULA = "cedula_digitada", "Cédula digitada"

    taller = models.ForeignKey(Taller, on_delete=models.CASCADE, related_name="participantes")
    expediente = models.ForeignKey(
        Expediente, null=True, blank=True, on_delete=models.SET_NULL, related_name="talleres"
    )
    cedula_digitada = models.CharField(max_length=13, blank=True)
    validado = models.BooleanField(default=False)
    asistio = models.BooleanField(default=True)
    origen = models.CharField(max_length=16, choices=Origen.choices)
    snapshot_academico = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "participante de taller"
        verbose_name_plural = "participantes de talleres"
        constraints = [
            models.UniqueConstraint(
                fields=["taller", "cedula_digitada"],
                name="uniq_taller_cedula",
                condition=models.Q(cedula_digitada__gt=""),
            )
        ]

    def __str__(self):
        return f"{self.cedula_digitada or self.expediente} @ {self.taller}"
