"""
Consultas de lectura de usuarios y perfiles.

La pantalla de gestión responde una pregunta que hasta ahora solo se podía
contestar a mano desde `/admin/`: quién atiende, en qué servicio, con qué rol
y si tiene horario. Sin lo último la lista engaña, porque un profesional
perfectamente dado de alta y sin franjas **no admite ninguna cita** y nada en
la ficha lo dice.
"""

from django.db.models import Count, Q

from .models import PerfilProfesional, Usuario


def perfiles_para_gestion(texto: str = "", seccion_id=None):
    """
    Los perfiles profesionales con lo que hace falta para gestionarlos.

    Incluye el conteo de franjas ACTIVAS —no el de todas—: una franja retirada
    se conserva para explicar una cita antigua, y contarla haría parecer que el
    profesional tiene horario cuando no lo tiene.
    """
    consulta = (
        PerfilProfesional.objects.select_related("usuario", "seccion")
        .prefetch_related("servicios")
        .annotate(franjas=Count("agendas", filter=Q(agendas__activa=True), distinct=True))
        .order_by("seccion__nombre", "usuario__last_name", "usuario__first_name")
    )
    if seccion_id:
        consulta = consulta.filter(seccion_id=seccion_id)

    texto = (texto or "").strip()
    if texto:
        for palabra in texto.split():
            consulta = consulta.filter(
                Q(usuario__first_name__icontains=palabra)
                | Q(usuario__last_name__icontains=palabra)
                | Q(usuario__username__icontains=palabra)
                | Q(usuario__cedula__icontains=palabra)
            )
    return consulta


def nombre_del_centinela() -> str:
    """
    El nombre de la fila que django-guardian crea para el usuario anónimo.

    Vive aquí y no repetido en cada sitio que lo necesita: ya hace falta en
    dos —la lista de cuentas sin ficha y el arranque de la portable— y dos
    copias se separan la primera vez que alguien cambia `ANONYMOUS_USER_NAME`.
    """
    from django.conf import settings
    from guardian.conf import settings as guardian

    return getattr(settings, "ANONYMOUS_USER_NAME", guardian.ANONYMOUS_USER_NAME)


def cuentas_de_persona():
    """
    Las cuentas que son de alguien. Todas menos el centinela de guardian.

    `Usuario.objects.exists()` SIEMPRE es cierto —la migración de guardian deja
    su fila—, así que «¿hay alguna cuenta todavía?» no se puede preguntar así.
    La portable lo preguntaba de esa forma y nunca reconocía la primera cuenta
    como primera: la creaba con «Consulta Restringida» y quien acababa de
    instalar el sistema entraba y no podía hacer nada.
    """
    return Usuario.objects.exclude(username=nombre_del_centinela())


def cuentas_sin_perfil():
    """
    Cuentas que no atienden: sin perfil profesional.

    Van en la pantalla a propósito. Son las que no aparecen en ninguna bandeja
    ni admiten cita, y la pregunta «¿por qué no sale Fulano?» se contesta aquí
    y no abriendo `/admin/` a ver si existe.

    Menos el centinela de django-guardian: `AnonymousUser` es una fila que la
    librería crea para colgar permisos por objeto del usuario anónimo, no una
    persona. Salía en la lista con su botón de «dar ficha» al lado, y darle
    ficha profesional al anónimo es exactamente lo que no debe poder hacerse
    desde ninguna pantalla.
    """
    return cuentas_de_persona().filter(perfil__isnull=True, is_active=True).order_by("username")
