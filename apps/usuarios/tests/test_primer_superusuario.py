"""
La primera cuenta del sistema tiene que poder gobernarlo.

`rol_principal` sale por omisión como «Consulta Restringida», así que la cuenta
de `createsuperuser` —la del día del despliegue, la única que existe— entraba y
veía seis módulos de diecisiete: ni Reportes, ni la Bitácora, ni la carga de la
base institucional. Quien acaba de instalar el sistema concluye que está roto.

Lo que NO cambia, y por eso está aquí: un administrador no ve contenido
clínico. `atenciones_visibles` le devuelve `.none()` por separación de
funciones, y el sello de Psicología sigue cerrado.
"""

import pytest

from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.mark.django_db
def test_el_superusuario_nace_administrador_general():
    cuenta = Usuario.objects.create_superuser(username="jefe", password=CLAVE)

    assert cuenta.rol_principal == Rol.ADMIN_GENERAL


@pytest.mark.django_db
def test_un_rol_pedido_expresamente_se_respeta():
    """El valor por omisión es una ayuda, no una imposición."""
    cuenta = Usuario.objects.create_superuser(
        username="raro", password=CLAVE, rol_principal=Rol.DIRECTOR
    )

    assert cuenta.rol_principal == Rol.DIRECTOR


@pytest.mark.django_db
def test_una_cuenta_normal_sigue_naciendo_con_consulta_restringida():
    """Lo que se abre es la primera cuenta, no todas."""
    cuenta = Usuario.objects.create_user(username="cualquiera", password=CLAVE)

    assert cuenta.rol_principal == Rol.CONSULTA


@pytest.mark.django_db
def test_el_superusuario_ve_los_modulos_de_gestion():
    from apps.core.navegacion import modulos_visibles
    from apps.expediente.tests.factories import crear_estructura

    crear_estructura()
    cuenta = Usuario.objects.create_superuser(username="jefe", password=CLAVE)

    etiquetas = {m.etiqueta for m in modulos_visibles(cuenta)}

    assert {"Reportes", "Bitácora", "Base institucional"} <= etiquetas


@pytest.mark.django_db
def test_el_superusuario_sigue_sin_ver_contenido_clinico():
    """
    Que gobierne no es que mire. `atenciones_visibles` devuelve `.none()` para
    cualquier administrador, y esto no lo toca.
    """
    from apps.expediente.models import Atencion
    from apps.usuarios import rbac

    cuenta = Usuario.objects.create_superuser(username="jefe", password=CLAVE)

    assert rbac.es_admin(cuenta)
    assert not rbac.atenciones_visibles(cuenta, Atencion.objects.all()).exists()
