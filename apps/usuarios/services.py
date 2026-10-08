"""Servicios de usuarios: acceso de emergencia (break the glass) y auditoría RBAC."""

from __future__ import annotations

from apps.auditoria.models import LogAuditoria


def registrar_break_glass(user, expediente_id, motivo, ip=None, user_agent=""):
    """
    Registra un acceso de emergencia justificado (informe 10.2, 14.5).
    Deja constancia destacada en la auditoría; la notificación al Director la
    dispara una señal a partir de este log.
    """
    return LogAuditoria.objects.create(
        usuario=user,
        rol_activo=getattr(user, "rol_principal", ""),
        accion=LogAuditoria.Accion.BREAK_GLASS,
        modulo="expediente",
        entidad="Expediente",
        entidad_id=str(expediente_id),
        expediente_id=expediente_id,
        detalle={"motivo": motivo},
        ip=ip,
        user_agent=user_agent[:255] if user_agent else "",
    )


# Lo que un profesional puede corregir de su propia ficha. Deliberadamente NO
# están aquí `servicios`, `seccion`, `rol_principal` ni `puede_firmar_digital`:
# de esos depende el RBAC, y quien los editara se ampliaría el acceso a sí
# mismo. Los asigna quien administra, desde el panel.
CAMPOS_CUENTA = ("first_name", "last_name", "cedula", "telefono", "email", "fecha_nacimiento")
CAMPOS_PERFIL = ("titulo", "registro_profesional", "denominacion_cargo")
# `fecha_nacimiento` llega como texto ISO ("YYYY-MM-DD") de un <input
# type="date">, o cadena vacía: no se le aplica `.strip()` como al resto.
CAMPOS_FECHA = ("fecha_nacimiento",)


def actualizar_mi_perfil(usuario, datos: dict):
    """
    Actualiza los datos propios del profesional y devuelve su perfil.

    La cédula se normaliza y se valida con el módulo 10: es la que identifica
    al firmante ante FirmaEC, así que una mal digitada aquí bloquearía la firma
    más tarde y en otro sitio.

    Se valida TODO antes de escribir nada. `ATOMIC_REQUESTS` envuelve la
    petición entera: registrar el rechazo y luego lanzar ValidationError
    revertiría el propio registro, así que aquí no se audita lo rechazado.
    """
    from django.core.exceptions import ValidationError
    from django.db import transaction

    from apps.academico.validators import normalizar_cedula, validar_cedula_ecuatoriana
    from apps.auditoria.models import LogAuditoria

    from .models import PerfilProfesional, Usuario

    cedula = datos.get("cedula", "")
    if cedula:
        cedula = normalizar_cedula(cedula)
        if not validar_cedula_ecuatoriana(cedula):
            raise ValidationError(f"La cédula {cedula} no es válida (módulo 10).")
        # `Usuario` explícito, no `type(usuario)`: desde una vista llega un
        # SimpleLazyObject y `type(...)` devuelve la envoltura, que no tiene
        # manager. Con un objeto real —como en las pruebas del servicio— sí
        # funcionaba, así que el fallo solo salía en pantalla.
        ajena = (
            Usuario.objects.filter(cedula=cedula)
            .exclude(pk=usuario.pk)
            .values_list("username", flat=True)
            .first()
        )
        if ajena:
            raise ValidationError("Esa cédula ya está registrada en otra cuenta.")

    fecha_nacimiento = datos.get("fecha_nacimiento", "")
    if fecha_nacimiento:
        from datetime import date

        from django.utils.dateparse import parse_date

        fecha = parse_date(fecha_nacimiento)
        if fecha is None:
            raise ValidationError("La fecha de nacimiento no es válida.")
        if fecha > date.today():
            raise ValidationError("La fecha de nacimiento no puede ser futura.")

    with transaction.atomic():
        for campo in CAMPOS_CUENTA:
            if campo not in datos:
                continue
            if campo == "cedula":
                # Única y admite NULL: dejarla en cadena vacía haría chocar a
                # la segunda cuenta que se guardara sin cédula.
                valor = cedula or None
            elif campo in CAMPOS_FECHA:
                # DateField.to_python la parsea al guardar; cadena vacía -> None.
                valor = datos[campo] or None
            else:
                valor = datos[campo].strip()
            setattr(usuario, campo, valor)
        usuario.save(update_fields=[c for c in CAMPOS_CUENTA if c in datos])

        perfil, _ = PerfilProfesional.objects.get_or_create(usuario=usuario)
        for campo in CAMPOS_PERFIL:
            if campo in datos:
                setattr(perfil, campo, datos[campo].strip())
        perfil.save(update_fields=[c for c in CAMPOS_PERFIL if c in datos] or None)

        LogAuditoria.objects.create(
            usuario=usuario,
            rol_activo=getattr(usuario, "rol_principal", ""),
            accion=LogAuditoria.Accion.UPDATE,
            modulo="usuarios",
            entidad="PerfilProfesional",
            entidad_id=str(perfil.pk),
            detalle={"campos": sorted(set(datos) & set(CAMPOS_CUENTA + CAMPOS_PERFIL))},
        )
    return perfil


# ============================================================
# Actividades esenciales del manual de puestos
# ============================================================


def agregar_actividad(perfil, descripcion: str, actividad_superior=None):
    """
    Agrega una actividad esencial al final de su lista.

    Sin `actividad_superior` es una fila de primer nivel (una de las diez a
    trece del manual). Con ella, es una sub-actividad de las que suelen
    acumularse bajo la última —"las demás que asigne el jefe inmediato"—; se
    numera dentro de esa lista propia, no en la general.

    El siguiente `orden` se calcula, no se recibe: quien agrega una actividad
    no tiene por qué saber cuántas hay ya, y dejarlo a su cargo abriría la
    puerta a huecos o choques de numeración.
    """
    from django.core.exceptions import ValidationError

    from .models import ActividadEsencial

    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise ValidationError("La actividad necesita una descripción.")

    if actividad_superior is not None and actividad_superior.perfil_id != perfil.pk:
        raise ValidationError("Esa actividad superior no pertenece a este perfil.")

    hermanas = ActividadEsencial.objects.filter(
        perfil=perfil, actividad_superior=actividad_superior
    )
    siguiente_orden = (hermanas.order_by("-orden").values_list("orden", flat=True).first() or 0) + 1

    return ActividadEsencial.objects.create(
        perfil=perfil,
        actividad_superior=actividad_superior,
        orden=siguiente_orden,
        descripcion=descripcion,
    )


def eliminar_actividad(actividad):
    """
    Quita una actividad esencial. Si tenía sub-actividades, se van con ella
    —`on_delete=CASCADE`—: no puede quedar una sub-actividad huérfana de la
    fila del manual que la contiene.
    """
    actividad.delete()


# ============================================================
# Gestión de perfiles (solo Administración General)
# ============================================================
#
# Lo que `actualizar_mi_perfil` deja fuera a propósito —servicios, sección, rol
# y firma digital— se asigna aquí. Hasta ahora solo desde `/admin/` de Django,
# que ni explica lo que concede ni deja un rastro legible.
#
# Y lo que se concede no es poca cosa: asignar el servicio de Psicología da
# acceso al contenido clínico sellado. Por eso cada cambio de servicios, rol o
# firma deja una entrada en la bitácora que dice QUÉ entró y QUÉ salió, no un
# «se actualizó el perfil» que obliga a comparar dos versiones para enterarse.


def _nombres(servicios) -> list[str]:
    return sorted(s.codigo for s in servicios)


def asignar_perfil(
    *,
    perfil,
    seccion=None,
    servicios=None,
    rol_principal: str | None = None,
    puede_firmar_digital: bool | None = None,
    usuario_que_asigna,
):
    """
    Asigna sección, servicios, rol y firma digital a un profesional.

    Solo la llama la pantalla de Administración General; el permiso se
    comprueba en la vista, que es donde está la petición. Aquí se protege lo
    que ninguna pantalla puede saltarse:

    - **Nadie se quita a sí mismo la administración.** Si el único
      administrador se degrada, no queda quien pueda devolverle el rol y la
      gestión de perfiles se cierra para todos. Es un callejón sin salida que
      solo se abre volviendo al shell.
    - **Lo concedido y lo retirado quedan escritos**, servicio por servicio.
    """
    from django.core.exceptions import ValidationError
    from django.db import transaction

    from apps.auditoria.models import LogAuditoria

    from .models import Rol

    antes = {
        "seccion": perfil.seccion.codigo if perfil.seccion else "",
        "servicios": _nombres(perfil.servicios.all()),
        "rol": perfil.usuario.rol_principal,
        "firma": perfil.puede_firmar_digital,
    }

    if (
        rol_principal is not None
        and perfil.usuario_id == usuario_que_asigna.pk
        and antes["rol"] == Rol.ADMIN_GENERAL
        and rol_principal != Rol.ADMIN_GENERAL
    ):
        raise ValidationError(
            "No puede quitarse a usted mismo la Administración General: si nadie "
            "más la tiene, se quedaría sin quien pueda devolvérsela."
        )

    with transaction.atomic():
        if seccion is not None:
            perfil.seccion = seccion
        if puede_firmar_digital is not None:
            perfil.puede_firmar_digital = puede_firmar_digital
        perfil.save()

        if servicios is not None:
            perfil.servicios.set(servicios)

        if rol_principal is not None:
            perfil.usuario.rol_principal = rol_principal
            perfil.usuario.save(update_fields=["rol_principal"])

        perfil.refresh_from_db()
        despues = {
            "seccion": perfil.seccion.codigo if perfil.seccion else "",
            "servicios": _nombres(perfil.servicios.all()),
            "rol": perfil.usuario.rol_principal,
            "firma": perfil.puede_firmar_digital,
        }
        concedidos = sorted(set(despues["servicios"]) - set(antes["servicios"]))
        retirados = sorted(set(antes["servicios"]) - set(despues["servicios"]))

        LogAuditoria.objects.create(
            usuario=usuario_que_asigna,
            rol_activo=getattr(usuario_que_asigna, "rol_principal", ""),
            accion=LogAuditoria.Accion.UPDATE,
            modulo="usuarios",
            entidad="PerfilProfesional",
            entidad_id=str(perfil.pk),
            detalle={
                "sobre": perfil.usuario.username,
                "antes": antes,
                "despues": despues,
                "servicios_concedidos": concedidos,
                "servicios_retirados": retirados,
            },
        )
    return perfil


def crear_perfil(*, usuario, usuario_que_asigna, **asignacion):
    """
    Da de alta la ficha profesional de una cuenta que no la tenía.

    Sin perfil, una cuenta no aparece en ninguna bandeja, no admite cita y no
    puede tener horario. Crear el perfil es lo que convierte una cuenta en
    alguien que atiende, así que va por el mismo camino auditado.
    """
    from django.conf import settings
    from django.core.exceptions import ValidationError
    from guardian.conf import settings as guardian

    from .models import PerfilProfesional

    # La lista ya lo esconde; aquí se niega. Un `pk` en el POST no es un
    # permiso, y `AnonymousUser` es la fila que django-guardian usa para colgar
    # los permisos del usuario anónimo: no es una persona y no atiende a nadie.
    centinela = getattr(settings, "ANONYMOUS_USER_NAME", guardian.ANONYMOUS_USER_NAME)
    if usuario.username == centinela:
        raise ValidationError("Esa no es una cuenta de persona: es el usuario anónimo interno.")

    if PerfilProfesional.objects.filter(usuario=usuario).exists():
        raise ValidationError("Esa cuenta ya tiene ficha profesional.")

    perfil = PerfilProfesional.objects.create(usuario=usuario)
    return asignar_perfil(perfil=perfil, usuario_que_asigna=usuario_que_asigna, **asignacion)
