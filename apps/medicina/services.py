"""
Lógica de negocio de Medicina.

Reglas clave:
- Cada AtencionMedicina debe existir dentro de una Atencion (informe 11.3).
- Exactamente un diagnóstico principal por atención.
- Al agregar un diagnóstico marcado como principal, cualquier otro anterior
  pierde la bandera (una sola verdad).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import CIE10, Servicio
from apps.expediente.models import Atencion, Expediente
from apps.expediente.services import construir_snapshot, verificar_profesional_del_servicio
from apps.usuarios.models import PerfilProfesional

from .models import AtencionMedicina, Diagnostico


@transaction.atomic
def crear_atencion_medicina(
    *,
    expediente: Expediente,
    profesional: PerfilProfesional,
    motivo: str = "",
    cita=None,
    usuario=None,
) -> AtencionMedicina:
    """
    Crea una Atencion + AtencionMedicina en una transacción.
    Toma automáticamente el servicio de Medicina y congela el snapshot.
    """
    try:
        servicio = Servicio.objects.get(codigo="medicina")
    except Servicio.DoesNotExist as exc:
        raise ValidationError("El servicio 'medicina' no está configurado.") from exc

    verificar_profesional_del_servicio(profesional, servicio)

    atencion = Atencion.objects.create(
        expediente=expediente,
        servicio=servicio,
        profesional=profesional,
        fecha_hora=timezone.now(),
        motivo_consulta=motivo,
        origen=Atencion.Origen.CITA if cita else Atencion.Origen.ESPONTANEA,
        snapshot_academico=construir_snapshot(expediente.persona),
        creado_por=usuario,
    )
    return AtencionMedicina.objects.create(atencion=atencion)


def agregar_diagnostico(
    atencion: Atencion,
    cie10_codigo: str,
    *,
    tipo: str = Diagnostico.TipoDx.PRESUNTIVO,
    condicion: str = Diagnostico.Condicion.PRIMERA,
    principal: bool = False,
    observacion: str = "",
) -> Diagnostico:
    """
    Agrega un diagnóstico a la atención. Si se marca `principal=True`, quita
    la bandera de cualquier diagnóstico previo. Rechaza si la atención ya
    está firmada (informe 4.2, inmutabilidad clínica).
    """
    if atencion.inmutable:
        raise ValidationError("No se puede modificar una atención firmada.")

    cie10 = CIE10.objects.get(codigo=cie10_codigo)

    if Diagnostico.objects.filter(atencion=atencion, cie10=cie10).exists():
        raise ValidationError(f"El diagnóstico {cie10_codigo} ya está registrado.")

    if principal:
        Diagnostico.objects.filter(atencion=atencion, principal=True).update(principal=False)

    return Diagnostico.objects.create(
        atencion=atencion,
        cie10=cie10,
        tipo=tipo,
        condicion=condicion,
        principal=principal,
        observacion=observacion,
    )


def cerrar_atencion(atencion: Atencion, usuario=None):
    """
    Cierra la atención (estado CERRADA). Requiere al menos un diagnóstico
    y que exista un diagnóstico principal.
    """
    if atencion.estado != Atencion.Estado.BORRADOR:
        raise ValidationError(
            f"Solo se cierran atenciones en borrador (actual: {atencion.estado})."
        )

    diags = list(Diagnostico.objects.filter(atencion=atencion))
    if not diags:
        raise ValidationError("La atención debe tener al menos un diagnóstico.")
    if not any(d.principal for d in diags):
        raise ValidationError("Debe marcarse un diagnóstico como principal.")

    atencion.estado = Atencion.Estado.CERRADA
    atencion.save(update_fields=["estado", "actualizado_en"])
    return atencion
