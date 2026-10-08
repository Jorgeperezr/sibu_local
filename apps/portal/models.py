"""
Portal de autogestión: vinculación de un usuario final con su expediente.

El portal es superficie pública. La vinculación es su único punto de entrada, y
por eso concentra las defensas: el enlace de verificación viaja al correo
institucional que consta en el dato académico —nunca a uno digitado— y el token
se guarda hasheado, con expiración y un solo uso.
"""

import hashlib

from django.db import models
from django.utils import timezone

from apps.expediente.models import Expediente
from apps.usuarios.models import Usuario


class VinculacionPortal(models.Model):
    """Asocia una cuenta del portal con un expediente, previa verificación."""

    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, related_name="vinculacion_portal"
    )
    expediente = models.OneToOneField(
        Expediente, on_delete=models.CASCADE, related_name="vinculacion_portal"
    )
    verificado = models.BooleanField(default=False)
    correo_destino = models.EmailField(
        help_text="Correo institucional al que se envió la verificación."
    )
    # Se guarda el hash, no el token: un volcado de la base no debe permitir
    # completar vinculaciones ajenas.
    token_hash = models.CharField(max_length=64, editable=False)
    token_expira_en = models.DateTimeField()
    verificado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vinculación del portal"
        verbose_name_plural = "vinculaciones del portal"

    def __str__(self):
        estado = "verificada" if self.verificado else "pendiente"
        return f"{self.usuario} ↔ expediente {self.expediente_id} ({estado})"

    @staticmethod
    def hashear(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @property
    def vigente(self) -> bool:
        return not self.verificado and timezone.now() <= self.token_expira_en
