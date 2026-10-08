"""
La gestión de perfiles: quién atiende, en qué servicio y con qué rol.

Hasta ahora esto solo se hacía desde `/admin/` de Django, que lista cuentas y
perfiles por separado, no dice los servicios ni si hay horario, y no deja un
rastro legible de lo que concede.

Y lo que concede no es poca cosa: **asignar el servicio de Psicología da acceso
a su contenido clínico sellado**. Por eso la pantalla es de Administración
General y nada más, y por eso cada cambio queda escrito con lo que entró y lo
que salió.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.core.models import Seccion, Servicio
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import PerfilProfesional, Rol, Usuario
from apps.usuarios.services import asignar_perfil, crear_perfil

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    admin = Usuario.objects.create_user(
        username="jefa", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )
    _, medico = crear_profesional("medico_g", est["medicina"], est["salud"])
    cliente = Client()
    assert cliente.login(username="jefa", password=CLAVE)
    return {"est": est, "admin": admin, "perfil": medico, "cliente": cliente}


# ------------------------------------------------------------------ el acceso


@pytest.mark.django_db
@pytest.mark.parametrize(
    "rol", [Rol.DIRECTOR, Rol.COORDINADOR, Rol.PROFESIONAL, Rol.ADMINISTRATIVO, Rol.CONSULTA]
)
def test_solo_administracion_general_gestiona_perfiles(escenario, rol):
    """
    Ni la Dirección ni la Coordinación: asignar servicios es conceder acceso, y
    uno de los servicios abre contenido sellado.
    """
    Usuario.objects.create_user(username=f"otro_{rol}", password=CLAVE, rol_principal=rol)
    cliente = Client()
    assert cliente.login(username=f"otro_{rol}", password=CLAVE)

    assert cliente.get(reverse("usuarios:gestion_perfiles")).status_code == 403
    assert (
        cliente.get(reverse("usuarios:editar_perfil", args=[escenario["perfil"].pk])).status_code
        == 403
    )


@pytest.mark.django_db
def test_el_alta_de_ficha_no_responde_a_un_get(escenario):
    """
    Crea una ficha: una vista que escribe no puede responder a un GET, o
    bastaría un `<img src="...">` ajeno para dar de alta a alguien.
    """
    suelto = Usuario.objects.create_user(username="suelto", password=CLAVE)

    respuesta = escenario["cliente"].get(reverse("usuarios:alta_perfil", args=[suelto.pk]))

    assert respuesta.status_code == 405
    assert not PerfilProfesional.objects.filter(usuario=suelto).exists()


# ------------------------------------------------------------------- asignar


@pytest.mark.django_db
def test_asignar_servicios_queda_escrito_con_lo_que_entra_y_lo_que_sale(escenario):
    """
    «Se actualizó el perfil» obliga a comparar dos versiones para enterarse de
    que alguien acaba de recibir acceso a Psicología. La bitácora lo dice.
    """
    asignar_perfil(
        perfil=escenario["perfil"],
        servicios=[escenario["est"]["psicologia"]],
        usuario_que_asigna=escenario["admin"],
    )

    log = LogAuditoria.objects.filter(entidad="PerfilProfesional").latest("fecha_hora")
    assert log.usuario == escenario["admin"]
    assert log.detalle["servicios_concedidos"] == ["psicologia"]
    assert log.detalle["servicios_retirados"] == ["medicina"]
    assert log.detalle["sobre"] == escenario["perfil"].usuario.username


@pytest.mark.django_db
def test_asignar_psicologia_no_da_acceso_a_quien_asigna(escenario):
    """
    El sello no se toca. Administración General reparte el acceso y sigue sin
    tenerlo: `atenciones_visibles` le devuelve cero por separación de funciones.
    """
    from apps.expediente.models import Atencion
    from apps.usuarios import rbac

    asignar_perfil(
        perfil=escenario["perfil"],
        servicios=[escenario["est"]["psicologia"]],
        usuario_que_asigna=escenario["admin"],
    )

    assert not rbac.atenciones_visibles(escenario["admin"], Atencion.objects.all()).exists()
    assert not rbac.puede_ver_servicio(escenario["admin"], escenario["est"]["psicologia"])


@pytest.mark.django_db
def test_nadie_se_quita_a_si_mismo_la_administracion(escenario):
    """
    Si el único administrador se degrada, no queda quien pueda devolverle el
    rol: la gestión de perfiles se cierra para todos y solo se reabre desde el
    shell. Es un callejón sin salida, no una decisión.
    """
    perfil_admin = PerfilProfesional.objects.create(usuario=escenario["admin"])

    with pytest.raises(ValidationError, match="No puede quitarse a usted mismo"):
        asignar_perfil(
            perfil=perfil_admin,
            rol_principal=Rol.PROFESIONAL,
            usuario_que_asigna=escenario["admin"],
        )

    escenario["admin"].refresh_from_db()
    assert escenario["admin"].rol_principal == Rol.ADMIN_GENERAL


@pytest.mark.django_db
def test_se_puede_degradar_a_otro_administrador(escenario):
    """Lo que se impide es el callejón sin salida propio, no gestionar roles."""
    otro = Usuario.objects.create_user(
        username="otro_admin", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )
    perfil = PerfilProfesional.objects.create(usuario=otro)

    asignar_perfil(
        perfil=perfil, rol_principal=Rol.PROFESIONAL, usuario_que_asigna=escenario["admin"]
    )

    otro.refresh_from_db()
    assert otro.rol_principal == Rol.PROFESIONAL


@pytest.mark.django_db
def test_no_se_duplica_la_ficha_de_quien_ya_la_tiene(escenario):
    with pytest.raises(ValidationError, match="ya tiene ficha"):
        crear_perfil(usuario=escenario["perfil"].usuario, usuario_que_asigna=escenario["admin"])


# ------------------------------------------------------------------ pantalla


@pytest.mark.django_db
def test_la_lista_avisa_de_quien_no_tiene_horario(escenario):
    """
    El desconcierto más común: un profesional bien dado de alta y sin franjas
    NO admite ninguna cita, y nada en su ficha lo advertía.
    """
    contenido = escenario["cliente"].get(reverse("usuarios:gestion_perfiles")).content.decode()

    assert "sin horario" in contenido
    assert escenario["perfil"].usuario.username in contenido


@pytest.mark.django_db
def test_la_lista_enseña_las_cuentas_sin_ficha(escenario):
    """La pregunta «¿por qué no sale Fulano?» se contesta aquí, no en /admin/."""
    Usuario.objects.create_user(username="recien_llegada", password=CLAVE)

    contenido = escenario["cliente"].get(reverse("usuarios:gestion_perfiles")).content.decode()

    assert "recien_llegada" in contenido
    assert "Cuentas sin ficha profesional" in contenido


@pytest.mark.django_db
def test_se_asigna_desde_la_pantalla(escenario):
    seccion = Seccion.objects.get(codigo="salud")
    respuesta = escenario["cliente"].post(
        reverse("usuarios:editar_perfil", args=[escenario["perfil"].pk]),
        {
            "seccion": seccion.pk,
            "servicios": [escenario["est"]["medicina"].pk, escenario["est"]["psicologia"].pk],
            "rol": Rol.PROFESIONAL,
            "firma": "1",
        },
        follow=True,
    )

    assert respuesta.status_code == 200
    escenario["perfil"].refresh_from_db()
    assert escenario["perfil"].servicios.count() == 2
    assert escenario["perfil"].puede_firmar_digital is True


@pytest.mark.django_db
def test_la_pantalla_marca_los_servicios_sellados(escenario):
    """
    Quien asigna tiene que ver cuál de las casillas abre contenido sellado.
    Una lista de nueve nombres iguales no lo dice.
    """
    contenido = (
        escenario["cliente"]
        .get(reverse("usuarios:editar_perfil", args=[escenario["perfil"].pk]))
        .content.decode()
    )

    assert "sellado" in contenido
    assert "concede acceso" in contenido


@pytest.mark.django_db
def test_se_da_ficha_a_una_cuenta_que_no_la_tenia(escenario):
    suelto = Usuario.objects.create_user(username="suelto2", password=CLAVE)

    respuesta = escenario["cliente"].post(
        reverse("usuarios:alta_perfil", args=[suelto.pk]), follow=True
    )

    assert respuesta.status_code == 200
    assert PerfilProfesional.objects.filter(usuario=suelto).exists()


@pytest.mark.django_db
def test_el_menu_ofrece_perfiles_solo_a_administracion(escenario):
    from apps.core.navegacion import modulos_visibles

    assert "Perfiles" in {m.etiqueta for m in modulos_visibles(escenario["admin"])}

    director = Usuario.objects.create_user(
        username="dir", password=CLAVE, rol_principal=Rol.DIRECTOR
    )
    assert "Perfiles" not in {m.etiqueta for m in modulos_visibles(director)}


# ---------------------------------------------------- lo que no se toca aquí


@pytest.mark.django_db
def test_mi_perfil_sigue_sin_aceptar_servicios_ni_rol(escenario):
    """
    Lo de siempre: que exista una pantalla donde SÍ se asignan no relaja la
    propia, que sería una vía para ampliarse el acceso a uno mismo.
    """
    usuario = escenario["perfil"].usuario
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)

    cliente.post(
        reverse("usuarios:mi_perfil"),
        {
            "first_name": "Ana",
            "last_name": "Prueba",
            "servicios": [Servicio.objects.get(codigo="psicologia").pk],
            "rol_principal": Rol.ADMIN_GENERAL,
        },
    )

    usuario.refresh_from_db()
    escenario["perfil"].refresh_from_db()
    assert usuario.rol_principal != Rol.ADMIN_GENERAL
    assert [s.codigo for s in escenario["perfil"].servicios.all()] == ["medicina"]


@pytest.mark.django_db
def test_el_usuario_anonimo_interno_no_es_una_persona(escenario):
    """
    `AnonymousUser` es la fila que django-guardian crea para colgar los
    permisos por objeto del usuario anónimo. Salía en la lista de cuentas sin
    ficha, con su botón de «dar ficha» al lado.

    Se esconde de la lista Y se niega en el servicio: un `pk` en el POST no es
    un permiso.
    """
    from django.conf import settings
    from guardian.conf import settings as guardian

    # Ya existe: lo crea la propia migración de guardian, que es justamente por
    # lo que aparecía en la lista sin que nadie lo hubiera dado de alta.
    nombre = getattr(settings, "ANONYMOUS_USER_NAME", guardian.ANONYMOUS_USER_NAME)
    anonimo = Usuario.objects.get(username=nombre)

    contenido = escenario["cliente"].get(reverse("usuarios:gestion_perfiles")).content.decode()
    assert nombre not in contenido

    with pytest.raises(ValidationError, match="usuario anónimo interno"):
        crear_perfil(usuario=anonimo, usuario_que_asigna=escenario["admin"])
    assert not PerfilProfesional.objects.filter(usuario=anonimo).exists()
