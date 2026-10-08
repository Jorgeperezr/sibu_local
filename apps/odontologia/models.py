"""Historia clínica odontológica con odontograma FDI (informe 6.3)."""

from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion
from apps.usuarios.models import PerfilProfesional

# Piezas válidas en notación FDI: permanentes (11-48) y temporales (51-85).
CUADRANTES_PERMANENTES = (1, 2, 3, 4)
CUADRANTES_TEMPORALES = (5, 6, 7, 8)


def piezas_validas() -> set[str]:
    """Conjunto de piezas FDI válidas: 11-18, 21-28... y temporales 51-55…"""
    piezas = set()
    for cuadrante in CUADRANTES_PERMANENTES:
        for pieza in range(1, 9):
            piezas.add(f"{cuadrante}{pieza}")
    for cuadrante in CUADRANTES_TEMPORALES:
        for pieza in range(1, 6):
            piezas.add(f"{cuadrante}{pieza}")
    return piezas


class EstadoPieza(models.TextChoices):
    """
    Estados del odontograma. Los que cuentan para el índice CPO-D se
    identifican en `apps.odontologia.services.CPOD_CARIADO/PERDIDO/OBTURADO`.
    """

    SANO = "sano", "Sano"
    CARIADO = "cariado", "Cariado"
    OBTURADO = "obturado", "Obturado"
    PERDIDO = "perdido", "Perdido por caries"
    EXTRAIDO_OTRO = "extraido_otro", "Extraído por otra causa"
    CORONA = "corona", "Corona"
    SELLANTE = "sellante", "Sellante"
    PROTESIS = "protesis", "Prótesis"
    IMPLANTE = "implante", "Implante"
    AUSENTE = "ausente", "Ausente (no erupcionado)"


class AtencionOdontologia(models.Model):
    """Extensión OneToOne de Atencion para el servicio de Odontología."""

    atencion = models.OneToOneField(
        Atencion, on_delete=models.CASCADE, primary_key=True, related_name="odontologia"
    )
    examen_estomatognatico = models.JSONField(
        default=dict, blank=True, help_text="{region: hallazgos} — labios, lengua, paladar…"
    )
    indices = models.JSONField(
        default=dict,
        blank=True,
        help_text="Calculados por services.calcular_indices: cpod, componentes, placa",
    )
    plan_tratamiento = models.TextField(blank=True)
    indicaciones = models.TextField(blank=True)
    proxima_cita_sugerida = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "atención de odontología"
        verbose_name_plural = "atenciones de odontología"

    def __str__(self):
        return f"HC odontológica: {self.atencion}"


class OdontogramaDetalle(models.Model):
    """
    Estado de una pieza (o superficie) en un momento dado.

    `tipo=inicial` es el levantamiento del odontograma; `tipo=evolucion` son los
    cambios producto del tratamiento. Se conserva el histórico completo: nunca
    se sobrescribe un registro previo, se agrega uno nuevo.
    """

    class TipoRegistro(models.TextChoices):
        INICIAL = "inicial", "Inicial"
        EVOLUCION = "evolucion", "Evolución"

    atencion = models.ForeignKey(Atencion, on_delete=models.CASCADE, related_name="odontograma")
    pieza_fdi = models.CharField(max_length=2, help_text="Notación FDI de dos dígitos")
    superficie = models.CharField(
        max_length=2, blank=True, help_text="V, L, M, D, O (vacío = pieza completa)"
    )
    estado_codigo = models.CharField(max_length=20, choices=EstadoPieza.choices)
    tipo = models.CharField(
        max_length=10, choices=TipoRegistro.choices, default=TipoRegistro.INICIAL
    )
    observacion = models.CharField(max_length=255, blank=True)
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "detalle de odontograma"
        verbose_name_plural = "detalles de odontograma"
        ordering = ["pieza_fdi", "superficie"]
        indexes = [models.Index(fields=["atencion", "pieza_fdi"])]

    def __str__(self):
        sup = f".{self.superficie}" if self.superficie else ""
        return f"Pieza {self.pieza_fdi}{sup} — {self.get_estado_codigo_display()}"


class Procedimiento(ModeloBase):
    """
    Procedimiento odontológico ejecutado (informe 6.3).

    El catálogo de procedimientos vive en `CatalogoProcedimiento` para que la
    Unidad pueda mantenerlo sin tocar código.
    """

    atencion = models.ForeignKey(
        Atencion, on_delete=models.CASCADE, related_name="procedimientos_odonto"
    )
    catalogo = models.ForeignKey(
        "odontologia.CatalogoProcedimiento", on_delete=models.PROTECT, related_name="ejecuciones"
    )
    pieza_fdi = models.CharField(max_length=2, blank=True)
    superficie = models.CharField(max_length=2, blank=True)
    ejecutado_por = models.ForeignKey(
        PerfilProfesional, on_delete=models.PROTECT, related_name="procedimientos_odonto"
    )
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "procedimiento odontológico"
        verbose_name_plural = "procedimientos odontológicos"
        ordering = ["-creado_en"]

    def __str__(self):
        pieza = f" (pieza {self.pieza_fdi})" if self.pieza_fdi else ""
        return f"{self.catalogo.nombre}{pieza}"


class CatalogoProcedimiento(models.Model):
    """Catálogo editable de procedimientos odontológicos."""

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=150)
    requiere_pieza = models.BooleanField(
        default=True, help_text="Si es falso, aplica a boca completa (ej. profilaxis)."
    )
    estado_resultante = models.CharField(
        max_length=20,
        choices=EstadoPieza.choices,
        blank=True,
        help_text="Estado en que queda la pieza tras el procedimiento (ej. obturado).",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "procedimiento del catálogo"
        verbose_name_plural = "catálogo de procedimientos"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"
