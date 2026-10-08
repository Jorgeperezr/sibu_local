"""
Que la documentación no prometa cosas que el código no tiene.

Una guía que nombra un comando inexistente o enlaza a un archivo borrado es
peor que ninguna: se sigue al pie de la letra hasta que falla, y entonces no se
sabe si falló el sistema o la guía.

Esto no comprueba que lo escrito sea CIERTO —eso no lo puede hacer una
prueba— sino que lo que nombra exista.
"""

import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[3]
DOCS = list((RAIZ / "docs").glob("*.md")) + [RAIZ / "README.md"]


def test_hay_documentacion_que_revisar():
    """Si la ruta cambia y esto queda vacío, las pruebas de abajo pasarían solas."""
    assert len(DOCS) >= 5


@pytest.mark.parametrize("documento", DOCS, ids=lambda d: d.name)
def test_los_enlaces_a_archivos_del_repo_existen(documento):
    rotos = []
    for destino in re.findall(r"\]\((?!https?:)([^)#]+)", documento.read_text()):
        ruta = (documento.parent / destino).resolve()
        if not ruta.exists():
            rotos.append(destino)
    assert rotos == [], f"{documento.name} enlaza a lo que no está: {rotos}"


@pytest.mark.parametrize("documento", DOCS, ids=lambda d: d.name)
def test_los_comandos_de_manage_que_se_nombran_existen(documento):
    """
    `manage.py preparar`, `revisar_datos`, `cuentas`… Si se renombra uno y la
    guía sigue nombrando el viejo, quien la siga se queda parado.
    """
    from django.core.management import get_commands

    conocidos = set(get_commands())
    nombrados = set(re.findall(r"manage\.py ([a-z_]+)", documento.read_text()))
    # `python manage.py shell` y demás incorporados de Django también cuentan.
    faltan = sorted(nombrados - conocidos)
    assert faltan == [], f"{documento.name} nombra comandos inexistentes: {faltan}"


@pytest.mark.parametrize("documento", DOCS, ids=lambda d: d.name)
def test_los_objetivos_de_make_que_se_nombran_existen(documento):
    objetivos = set(re.findall(r"^([a-z-]+):", (RAIZ / "Makefile").read_text(), flags=re.MULTILINE))
    nombrados = set(re.findall(r"`?make ([a-z-]+)`?", documento.read_text()))
    faltan = sorted(nombrados - objetivos)
    assert faltan == [], f"{documento.name} nombra objetivos de make inexistentes: {faltan}"


def test_seguridad_nombra_funciones_que_existen():
    """
    El documento de seguridad describe funciones concretas del RBAC. Si alguna
    se renombra, el documento pasa a describir un sistema que no está.
    """
    from apps.expediente import services as expediente
    from apps.reportes import exportacion
    from apps.reportes import services as reportes
    from apps.usuarios import permissions, rbac

    texto = (RAIZ / "docs" / "SEGURIDAD.md").read_text()
    for nombre, modulo in (
        # Las dos que sostienen lo que el documento promete de los anexos: una
        # decide si un servicio puede sacar nombres, la otra es el único sitio
        # donde se clasifica, que es lo que impide que un anexo contradiga a la
        # cifra que respalda.
        ("verificar_exportable", exportacion),
        ("etiquetar", reportes),
        ("puede_ver_expediente", rbac),
        ("puede_ver_atencion", rbac),
        ("atenciones_visibles", rbac),
        ("visible_para_personal", rbac),
        ("SERVICIOS_CONFIDENCIALES", rbac),
        ("verificar_profesional_del_servicio", expediente),
        ("EsPersonalDeLaUnidad", permissions),
        ("PuedeVerAtencion", permissions),
    ):
        assert nombre in texto, f"SEGURIDAD.md ya no menciona {nombre}"
        assert hasattr(modulo, nombre), f"{nombre} ya no existe en {modulo.__name__}"
