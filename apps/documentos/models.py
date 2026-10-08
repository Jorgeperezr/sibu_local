"""
Gestión documental. Los anexos clínicos se guardan en almacén local cifrado;
las evidencias de talleres en Google Drive institucional (informe 5.2, 14.10).
"""

from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion, Expediente


class DocumentoAnexo(ModeloBase):
    class Almacenamiento(models.TextChoices):
        LOCAL = "local", "Almacén local cifrado"
        GDRIVE = "gdrive", "Google Drive institucional"

    expediente = models.ForeignKey(
        Expediente, null=True, blank=True, on_delete=models.CASCADE, related_name="documentos"
    )
    atencion = models.ForeignKey(
        Atencion, null=True, blank=True, on_delete=models.CASCADE, related_name="documentos"
    )
    taller = models.ForeignKey(
        "talleres.Taller",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidencias",
    )
    modulo = models.CharField(max_length=40)
    tipo_documento = models.CharField(max_length=60)
    nombre_archivo = models.CharField(max_length=255)
    almacenamiento = models.CharField(
        max_length=8, choices=Almacenamiento.choices, default=Almacenamiento.LOCAL
    )
    ruta_cifrada = models.CharField(max_length=500, blank=True)
    gdrive_file_id = models.CharField(max_length=120, blank=True)
    gdrive_url = models.URLField(blank=True)
    mime = models.CharField(max_length=100, blank=True)
    tamano = models.PositiveIntegerField(default=0)
    hash_sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "documento anexo"
        verbose_name_plural = "documentos anexos"
