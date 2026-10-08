"""
Modelos base y catálogos transversales de SIBU.

`ModeloBase` aporta soft-delete, marcas de tiempo y trazabilidad de autoría;
todos los modelos de negocio del sistema heredan de aquí para garantizar que
ningún registro se borre físicamente (requisito de integridad clínica y
auditoría del informe técnico, secciones 4.2 y 14.9).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def vivos(self):
        return self.filter(eliminado_en__isnull=True)

    def eliminados(self):
        return self.filter(eliminado_en__isnull=False)


class ModeloBaseManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).vivos()

    def todos(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class ModeloBase(models.Model):
    """Base abstracta: timestamps, autoría y borrado lógico."""

    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    eliminado_en = models.DateTimeField(null=True, blank=True)
    eliminado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = ModeloBaseManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, usuario=None):
        """Borrado lógico. El borrado físico está deshabilitado por diseño."""
        self.eliminado_en = timezone.now()
        if usuario is not None:
            self.eliminado_por = usuario
        self.save(update_fields=["eliminado_en", "eliminado_por"])

    def eliminado(self):
        return self.eliminado_en is not None


class Seccion(ModeloBase):
    """Sección organizativa de la Unidad (Salud, Psicopedagógica, Trabajo Social, Becas)."""

    nombre = models.CharField(max_length=120, unique=True)
    codigo = models.SlugField(max_length=30, unique=True)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "sección"
        verbose_name_plural = "secciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Servicio(ModeloBase):
    """Servicio concreto (Medicina, Enfermería, ... Becas)."""

    seccion = models.ForeignKey(Seccion, on_delete=models.PROTECT, related_name="servicios")
    nombre = models.CharField(max_length=120)
    codigo = models.SlugField(max_length=30, unique=True)
    permite_talleres = models.BooleanField(
        default=False,
        help_text="Habilita el registro de talleres para este servicio (art. 6.10 del informe).",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "servicio"
        verbose_name_plural = "servicios"
        ordering = ["seccion__nombre", "nombre"]

    def __str__(self):
        return f"{self.nombre}"


class PeriodoAcademico(ModeloBase):
    """Período académico de la UNL. Ancla temporal de cargas y snapshots."""

    codigo = models.CharField(max_length=20, unique=True, help_text="Ej.: 2026-1")
    nombre = models.CharField(max_length=80)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    vigente = models.BooleanField(default=False)

    class Meta:
        verbose_name = "período académico"
        verbose_name_plural = "períodos académicos"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return self.codigo


class CIE10(models.Model):
    """Catálogo de diagnósticos CIE-10 (cargado por fixture/comando)."""

    codigo = models.CharField(max_length=10, primary_key=True)
    descripcion = models.CharField(max_length=255)
    capitulo = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "CIE-10"
        verbose_name_plural = "catálogo CIE-10"
        indexes = [models.Index(fields=["descripcion"])]

    def __str__(self):
        return f"{self.codigo} — {self.descripcion}"


class ParametroSistema(ModeloBase):
    """Parámetros configurables sin redepliegue (clave/valor tipado en JSON)."""

    clave = models.CharField(max_length=80, unique=True)
    valor = models.JSONField(default=dict)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "parámetro del sistema"
        verbose_name_plural = "parámetros del sistema"

    def __str__(self):
        return self.clave
