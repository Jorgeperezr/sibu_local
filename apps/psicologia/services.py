"""
Lógica de negocio de Psicología (informe 6.6).

El contenido está sellado por RBAC; estos servicios asumen que quien los invoca
ya pasó el control de acceso (las vistas y la API lo aplican).

Protocolo de riesgo alto: notifica al coordinador de sección SIN contenido
clínico. El coordinador sabe que hay un caso y a quién contactar, pero no puede
leer la ficha — coherente con el sello confirmado por el cliente.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Atencion, Expediente
from apps.expediente.services import construir_snapshot, verificar_profesional_del_servicio
from apps.usuarios.models import PerfilProfesional

from .models import (
    AplicacionEscala,
    EscalaPsicometrica,
    FichaPsicologica,
    SesionPsicologica,
)


@transaction.atomic
def crear_ficha(
    *, expediente: Expediente, profesional: PerfilProfesional, motivo: str, usuario=None
) -> FichaPsicologica:
    """Abre un proceso psicológico (Atencion + FichaPsicologica)."""
    if not motivo:
        raise ValidationError("El motivo de consulta es obligatorio.")
    if proceso_activo(expediente) is not None:
        raise ValidationError(
            "El paciente ya tiene un proceso psicológico activo. "
            "Cierre el anterior antes de abrir uno nuevo."
        )
    try:
        servicio = Servicio.objects.get(codigo="psicologia")
    except Servicio.DoesNotExist as exc:
        raise ValidationError("El servicio 'psicologia' no está configurado.") from exc

    verificar_profesional_del_servicio(profesional, servicio)

    atencion = Atencion.objects.create(
        expediente=expediente,
        servicio=servicio,
        profesional=profesional,
        fecha_hora=timezone.now(),
        motivo_consulta=motivo,
        snapshot_academico=construir_snapshot(expediente.persona),
        creado_por=usuario,
    )
    return FichaPsicologica.objects.create(atencion=atencion, motivo=motivo)


def proceso_activo(expediente: Expediente) -> FichaPsicologica | None:
    """Ficha con proceso activo del paciente, si la hay."""
    return (
        FichaPsicologica.objects.filter(
            atencion__expediente=expediente, estado_proceso=FichaPsicologica.Estado.ACTIVO
        )
        .order_by("-atencion__fecha_hora")
        .first()
    )


@transaction.atomic
def registrar_sesion(
    ficha: FichaPsicologica,
    *,
    profesional: PerfilProfesional,
    evolucion: str,
    temas: str = "",
    tecnicas: str = "",
    tareas: str = "",
    fecha=None,
    proxima_sesion=None,
) -> SesionPsicologica:
    """Registra una sesión. La numeración es automática y correlativa por ficha."""
    if ficha.atencion.inmutable:
        raise ValidationError("No se pueden agregar sesiones a una atención firmada.")
    if ficha.estado_proceso != FichaPsicologica.Estado.ACTIVO:
        raise ValidationError(
            f"El proceso está {ficha.get_estado_proceso_display()}; no admite nuevas sesiones."
        )
    if not evolucion:
        raise ValidationError("La evolución de la sesión es obligatoria.")

    ultimo = ficha.sesiones.aggregate(m=Max("numero"))["m"] or 0
    return SesionPsicologica.objects.create(
        ficha=ficha,
        numero=ultimo + 1,
        fecha=fecha or timezone.localdate(),
        profesional=profesional,
        temas=temas,
        tecnicas=tecnicas,
        evolucion=evolucion,
        tareas=tareas,
        proxima_sesion=proxima_sesion,
    )


def aplicar_escala(
    ficha: FichaPsicologica, codigo_escala: str, puntaje: int, *, aplicado_por=None
) -> AplicacionEscala:
    """
    Aplica una escala del catálogo y guarda su interpretación según los tramos.

    Si el tramo está marcado como alerta, eleva el riesgo de la ficha a ALTO y
    dispara el protocolo.
    """
    escala = EscalaPsicometrica.objects.get(codigo=codigo_escala, activo=True)
    if not (escala.puntaje_min <= puntaje <= escala.puntaje_max):
        raise ValidationError(
            f"El puntaje {puntaje} está fuera del rango de {escala.codigo} "
            f"({escala.puntaje_min}-{escala.puntaje_max})."
        )

    tramo = escala.interpretar(puntaje)
    aplicacion = AplicacionEscala.objects.create(
        ficha=ficha,
        escala_catalogo=escala,
        escala=escala.nombre,
        puntaje=str(puntaje),
        interpretacion=tramo.get("etiqueta", ""),
        alerta=bool(tramo.get("alerta", False)),
        fecha=timezone.localdate(),
    )
    if aplicacion.alerta and ficha.riesgo_nivel != FichaPsicologica.Riesgo.ALTO:
        marcar_riesgo(
            ficha,
            FichaPsicologica.Riesgo.ALTO,
            nota=f"Elevado automáticamente por {escala.codigo} = {puntaje} "
            f"({tramo.get('etiqueta', '')}).",
        )
    return aplicacion


def marcar_riesgo(ficha: FichaPsicologica, nivel: str, nota: str) -> FichaPsicologica:
    """
    Fija el nivel de riesgo. Si es ALTO, dispara el protocolo de notificación.

    La nota clínica NO sale del servicio: la notificación al coordinador solo
    informa que existe un caso de riesgo y a quién contactar.
    """
    if nivel not in FichaPsicologica.Riesgo.values:
        raise ValidationError(f"Nivel de riesgo '{nivel}' no válido.")
    if not nota:
        raise ValidationError("Debe registrar la nota que sustenta el nivel de riesgo.")

    ficha.riesgo_nivel = nivel
    ficha.nota_riesgo = nota
    ficha.save(update_fields=["riesgo_nivel", "nota_riesgo"])

    if nivel == FichaPsicologica.Riesgo.ALTO:
        _notificar_riesgo_alto(ficha)
    return ficha


def _notificar_riesgo_alto(ficha: FichaPsicologica) -> None:
    """
    Notifica al coordinador de sección SIN exponer contenido clínico.

    El coordinador no puede abrir la ficha (RBAC lo impide); la notificación
    existe para que active el acompañamiento institucional contactando al
    profesional tratante.
    """
    from apps.notificaciones.models import Notificacion
    from apps.usuarios.models import Rol, Usuario

    tratante = ficha.atencion.profesional
    seccion = ficha.atencion.servicio.seccion

    coordinadores = Usuario.objects.filter(rol_principal=Rol.COORDINADOR, perfil__seccion=seccion)
    for coordinador in coordinadores:
        Notificacion.objects.create(
            usuario=coordinador,
            tipo="riesgo_psicologia",
            titulo="Caso de riesgo alto en Psicología",
            mensaje=(
                f"El servicio de Psicología registró un caso de riesgo alto. "
                f"Por confidencialidad no se detalla el contenido clínico. "
                f"Contacte al profesional tratante: "
                f"{tratante.usuario.get_full_name() or tratante.usuario.username}."
            ),
            canal=Notificacion.Canal.IN_APP,
            referencia_tipo="FichaPsicologica",
            referencia_id=ficha.pk,
        )


def cerrar_proceso(ficha: FichaPsicologica, estado: str) -> FichaPsicologica:
    """Cierra el proceso (alta, abandono o derivación)."""
    finales = {
        FichaPsicologica.Estado.ALTA,
        FichaPsicologica.Estado.ABANDONO,
        FichaPsicologica.Estado.DERIVADO,
    }
    if estado not in finales:
        raise ValidationError(f"'{estado}' no es un estado de cierre válido.")
    if not ficha.sesiones.exists():
        raise ValidationError("No se puede cerrar un proceso sin ninguna sesión registrada.")

    ficha.estado_proceso = estado
    ficha.save(update_fields=["estado_proceso"])

    ficha.atencion.estado = Atencion.Estado.CERRADA
    ficha.atencion.save(update_fields=["estado", "actualizado_en"])
    return ficha
