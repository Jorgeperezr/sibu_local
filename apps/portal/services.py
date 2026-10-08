"""Vinculación y consultas del portal. Todo parte del expediente propio."""

import logging
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.academico.validators import normalizar_cedula, validar_cedula_ecuatoriana
from apps.auditoria.models import LogAuditoria
from apps.expediente.models import Expediente
from apps.usuarios.models import Rol

from .models import VinculacionPortal

logger = logging.getLogger(__name__)

TOKEN_VIGENCIA_HORAS = 48
MAX_CITAS_ACTIVAS_PORTAL = 3


def solicitar_vinculacion(usuario, cedula: str) -> VinculacionPortal:
    """
    Inicia la vinculación con el expediente de la cédula indicada.

    El enlace de verificación se envía SOLO al correo institucional que consta
    en el dato académico. Nunca a un correo digitado por el usuario: si el
    correo lo eligiera quien se registra, cualquiera vincularía el expediente
    de otra persona con su propia casilla. La posesión de la casilla
    institucional ES la prueba de identidad.
    """
    if usuario.rol_principal != Rol.USUARIO_FINAL:
        raise ValidationError("El portal es para estudiantes y beneficiarios.")
    if VinculacionPortal.objects.filter(usuario=usuario, verificado=True).exists():
        raise ValidationError("Su cuenta ya está vinculada.")

    cedula = normalizar_cedula(cedula)
    if not validar_cedula_ecuatoriana(cedula):
        raise ValidationError("La cédula no es válida.")

    expediente = Expediente.objects.filter(persona__cedula=cedula).select_related("persona").first()
    if expediente is None:
        raise ValidationError(
            "No existe un expediente con esa cédula. Acérquese a Bienestar "
            "Universitario para crearlo."
        )
    vinculada = VinculacionPortal.objects.filter(expediente=expediente, verificado=True).first()
    if vinculada and vinculada.usuario_id != usuario.pk:
        # Se registra el intento: puede ser un error o alguien probando.
        LogAuditoria.objects.create(
            usuario=usuario,
            accion=LogAuditoria.Accion.READ,
            modulo="portal",
            entidad="VinculacionPortal",
            entidad_id=str(vinculada.pk),
            resultado="rechazado",
            detalle={"motivo": "expediente ya vinculado a otra cuenta"},
        )
        raise ValidationError(
            "Ese expediente ya está vinculado a otra cuenta. Si no fue usted, "
            "repórtelo a Bienestar Universitario."
        )

    dato = expediente.persona.datos_academicos.order_by("-periodo__fecha_inicio").first()
    correo = getattr(dato, "email_institucional", "") or ""
    dominio = settings.SIBU.get("DOMINIO_CORREO_INSTITUCIONAL", "unl.edu.ec")
    if not correo or not correo.endswith(f"@{dominio}"):
        raise ValidationError(
            "Su expediente no tiene un correo institucional registrado. La "
            "vinculación debe hacerse presencialmente en Bienestar Universitario."
        )

    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        VinculacionPortal.objects.filter(usuario=usuario, verificado=False).delete()
        vinculacion = VinculacionPortal.objects.create(
            usuario=usuario,
            expediente=expediente,
            correo_destino=correo,
            token_hash=VinculacionPortal.hashear(token),
            token_expira_en=timezone.now() + timezone.timedelta(hours=TOKEN_VIGENCIA_HORAS),
        )
    send_mail(
        subject="SIBU — Confirme la vinculación de su cuenta",
        message=(
            f"Hola {expediente.persona.nombres}:\n\n"
            "Alguien (esperamos que usted) pidió vincular esta cuenta del portal de "
            "Bienestar Universitario con su expediente.\n\n"
            f"Código de confirmación: {token}\n\n"
            f"Caduca en {TOKEN_VIGENCIA_HORAS} horas. Si no fue usted, ignore este "
            "correo y repórtelo a Bienestar Universitario."
        ),
        from_email=None,
        recipient_list=[correo],
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        accion=LogAuditoria.Accion.CREATE,
        modulo="portal",
        entidad="VinculacionPortal",
        entidad_id=str(vinculacion.pk),
        expediente_id=expediente.pk,
        detalle={"correo_destino": correo},
    )
    return vinculacion


def confirmar_vinculacion(usuario, token: str) -> VinculacionPortal:
    """Confirma con el token recibido por correo. Un solo uso, con expiración."""
    import hmac

    vinculacion = VinculacionPortal.objects.filter(usuario=usuario, verificado=False).first()
    if vinculacion is None:
        raise ValidationError("No tiene una vinculación pendiente.")
    if timezone.now() > vinculacion.token_expira_en:
        raise ValidationError("El código caducó. Solicite la vinculación de nuevo.")
    if not hmac.compare_digest(vinculacion.token_hash, VinculacionPortal.hashear(token.strip())):
        raise ValidationError("El código no es correcto.")

    vinculacion.verificado = True
    vinculacion.verificado_en = timezone.now()
    vinculacion.save(update_fields=["verificado", "verificado_en"])
    LogAuditoria.objects.create(
        usuario=usuario,
        accion=LogAuditoria.Accion.UPDATE,
        modulo="portal",
        entidad="VinculacionPortal",
        entidad_id=str(vinculacion.pk),
        expediente_id=vinculacion.expediente_id,
        detalle={"verificada": True},
    )
    return vinculacion


def expediente_de(usuario):
    """El expediente vinculado y verificado del usuario, o None."""
    v = (
        VinculacionPortal.objects.filter(usuario=usuario, verificado=True)
        .select_related("expediente__persona")
        .first()
    )
    return v.expediente if v else None


# ---------------------------------------------------------------------------
# Consultas del panel: SIEMPRE filtradas por el expediente propio
# ---------------------------------------------------------------------------


def mis_citas(expediente):
    from apps.citas.models import Cita

    return (
        Cita.objects.filter(expediente=expediente)
        .select_related("servicio", "profesional__usuario")
        .order_by("-fecha_hora")[:30]
    )


def cancelar_mi_cita(expediente, cita_id: int, usuario):
    """Cancela una cita SOLO si pertenece al expediente vinculado."""
    from apps.citas import services as citas_services
    from apps.citas.models import Cita

    cita = Cita.objects.filter(pk=cita_id, expediente=expediente).first()
    if cita is None:
        # El mismo mensaje exista o no la cita ajena: no se confirma la
        # existencia de recursos de otros.
        raise ValidationError("La cita no existe o no le pertenece.")
    return citas_services.cancelar(
        cita, motivo="Cancelada por el estudiante en el portal", usuario=usuario
    )


def agendar_cita(expediente, *, servicio, profesional, fecha_hora, usuario):
    """Reserva validando el límite del portal y la agenda real."""
    from apps.citas import services as citas_services
    from apps.citas.models import Cita
    from apps.citas.services import ESTADOS_ACTIVOS

    activas = Cita.objects.filter(
        expediente=expediente, estado__in=ESTADOS_ACTIVOS, fecha_hora__gte=timezone.now()
    ).count()
    if activas >= MAX_CITAS_ACTIVAS_PORTAL:
        raise ValidationError(
            f"Ya tiene {activas} citas activas. Cancele alguna o acérquese a ventanilla."
        )
    return citas_services.reservar_cita(
        expediente=expediente,
        servicio=servicio,
        profesional=profesional,
        fecha_hora=fecha_hora,
        motivo="Agendada por el estudiante en el portal",
        origen=Cita.Origen.AUTOGESTION,
        usuario=usuario,
    )


def mis_resultados_publicados(expediente):
    """Solo resultados PUBLICADOS: lo no publicado aún no pasó la validación."""
    from apps.laboratorio.models import OrdenLaboratorio

    return (
        OrdenLaboratorio.objects.filter(
            atencion__expediente=expediente, estado=OrdenLaboratorio.Estado.PUBLICADO
        )
        .select_related("atencion__servicio")
        .order_by("-publicado_en")[:20]
    )


def mis_recetas(expediente):
    from apps.farmacia.models import Receta

    return (
        Receta.objects.filter(atencion__expediente=expediente)
        .exclude(estado=Receta.Estado.ANULADA)
        .prefetch_related("detalles__medicamento")
        .order_by("-creado_en")[:20]
    )


def mis_becas(expediente):
    from apps.becas.models import BecaBeneficiario

    return (
        BecaBeneficiario.objects.filter(expediente=expediente, eliminado_en__isnull=True)
        .select_related("tipo_beca", "periodo_desde")
        .order_by("-creado_en")
    )


def mis_talleres(expediente):
    from apps.talleres.models import TallerParticipante

    return (
        TallerParticipante.objects.filter(expediente=expediente)
        .select_related("taller__servicio")
        .order_by("-taller__fecha")[:20]
    )
