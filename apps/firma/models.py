"""
Firma electrónica de documentos clínicos vía FirmaEC (MINTEL).

La criptografía NO vive aquí. SIBU genera el PDF, obtiene un token del servicio
FirmaEC, y el usuario firma con la aplicación de escritorio FirmaEC instalada en
su equipo: el certificado .p12 y su contraseña nunca salen de esa máquina ni
llegan al servidor. SIBU solo recibe el PDF ya firmado.

Referencia: "Manual de Implementación Institucional FirmaEC Descentralizada
2.1.0" (MINTEL, 11/10/2021), secciones 11 y 12.
"""

import secrets

from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion
from apps.usuarios.models import Usuario


def _nueva_correlacion() -> str:
    """
    Token opaco que viaja dentro del nombre del archivo.

    FirmaEC devuelve el documento firmado con solo dos datos de correlación:
    `cedula` y `nombreDocumento` (manual 11.4.2). No hay un id nuestro en el
    callback, así que el vínculo con la solicitud tiene que ir en el nombre.
    Debe ser impredecible: el callback es un endpoint expuesto y el nombre es,
    en la práctica, parte de su autenticación.
    """
    return secrets.token_urlsafe(32)


class SolicitudFirma(ModeloBase):
    """Una petición de firma en curso. Ciclo: preparada → enviada → firmada."""

    class Estado(models.TextChoices):
        PREPARADA = "preparada", "PDF generado, sin token"
        ENVIADA = "enviada", "Token obtenido, esperando al firmador"
        FIRMADA = "firmada", "Documento firmado y almacenado"
        FALLIDA = "fallida", "Rechazada o con error"
        EXPIRADA = "expirada", "El token caducó sin firmarse"

    correlacion = models.CharField(
        max_length=64, unique=True, default=_nueva_correlacion, editable=False
    )
    atencion = models.ForeignKey(
        Atencion, on_delete=models.CASCADE, related_name="solicitudes_firma"
    )
    documento_ref_tipo = models.CharField(max_length=40)
    documento_ref_id = models.PositiveBigIntegerField()
    tipo_documento = models.CharField(max_length=60, default="informe")

    solicitante = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="solicitudes_firma"
    )
    # Se congela al crear: el callback trae la cédula del firmante y tiene que
    # coincidir con la de quien pidió firmar, no con la del usuario "actual".
    cedula_solicitante = models.CharField(max_length=13)

    nombre_documento = models.CharField(max_length=255)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PREPARADA)

    pdf_original = models.BinaryField(editable=False)
    hash_original = models.CharField(max_length=64)
    pdf_firmado = models.BinaryField(null=True, blank=True, editable=False)
    hash_firmado = models.CharField(max_length=64, blank=True)

    token_expira_en = models.DateTimeField(null=True, blank=True)
    razon = models.CharField(max_length=70, blank=True)
    certificado = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "solicitud de firma"
        verbose_name_plural = "solicitudes de firma"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["documento_ref_tipo", "documento_ref_id"]),
            models.Index(fields=["estado"]),
        ]

    def __str__(self):
        return f"Firma {self.nombre_documento} ({self.get_estado_display()})"

    @property
    def abierta(self) -> bool:
        return self.estado in (self.Estado.PREPARADA, self.Estado.ENVIADA)


class FirmaDocumento(models.Model):
    """Registro final e inmutable de una firma aplicada."""

    class TipoFirma(models.TextChoices):
        ELECTRONICA = "electronica", "Electrónica simple"
        DIGITAL = "digital_certificado", "Digital con certificado"

    documento_ref_tipo = models.CharField(
        max_length=40, help_text="Modelo firmado (p. ej. atencion, receta)."
    )
    documento_ref_id = models.PositiveBigIntegerField()
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="firmas")
    tipo_firma = models.CharField(max_length=20, choices=TipoFirma.choices)
    hash_documento = models.CharField(max_length=64)
    sello_tiempo = models.DateTimeField(auto_now_add=True)
    certificado_serial = models.CharField(max_length=120, blank=True)
    valida = models.BooleanField(default=True)

    solicitud = models.OneToOneField(
        SolicitudFirma,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="firma",
    )
    firmante_nombre = models.CharField(max_length=200, blank=True)
    firmante_cedula = models.CharField(max_length=13, blank=True)
    entidad_certificadora = models.CharField(max_length=120, blank=True)
    fecha_firma = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "firma de documento"
        verbose_name_plural = "firmas de documentos"
        indexes = [models.Index(fields=["documento_ref_tipo", "documento_ref_id"])]

    def __str__(self):
        return (
            f"Firma {self.get_tipo_firma_display()} de "
            f"{self.documento_ref_tipo}#{self.documento_ref_id}"
        )
