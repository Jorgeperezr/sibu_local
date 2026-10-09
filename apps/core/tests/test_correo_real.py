"""
Sin SMTP, el sistema no puede decir que envió nada.

Con el backend de archivo —el de la portable— `send_mail` **no falla**:
escribe el mensaje en una carpeta y devuelve 1. El sistema lo tomaba por
entregado:

- Laboratorio registraba «Informe enviado a fulano@unl.edu.ec», estado
  ENVIADA, sobre un resultado que el paciente no iba a leer nunca. Un
  resultado clínico dado por entregado sin entregar.
- El portal creaba la vinculación y dejaba al estudiante esperando un código
  de confirmación escrito en una carpeta del computador del profesional. Y ese
  código ES la prueba de identidad de todo el portal.

La regla es la de siempre: el sistema informa, no decide, y no afirma lo que no
sabe. Sin correo, los resultados se entregan en ventanilla —que es exactamente
lo que ya se decía cuando la persona no tenía correo registrado— y la
vinculación se hace presencialmente.
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.core.correo import hay_correo_real
from apps.expediente.tests.factories import (
    crear_atencion,
    crear_estructura,
    crear_expediente,
    crear_profesional,
)

ARCHIVO = "django.core.mail.backends.filebased.EmailBackend"
CONSOLA = "django.core.mail.backends.console.EmailBackend"
DUMMY = "django.core.mail.backends.dummy.EmailBackend"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"


# --------------------------------------------------------------- la pregunta


@pytest.mark.parametrize("backend", [ARCHIVO, CONSOLA, DUMMY])
def test_los_backends_que_escriben_no_envian(settings, backend):
    settings.EMAIL_BACKEND = backend

    assert hay_correo_real() is False


def test_el_backend_de_las_pruebas_si_cuenta_como_correo(settings):
    """
    `locmem` estaba en la lista de los que no envían, y era un error caro.

    Guarda el mensaje en `mail.outbox`, que es exactamente el buzón que abre
    una prueba para comprobar que el aviso salió. Tratarlo como «no envía»
    apagaba el envío justo en el entorno donde se comprueba: seis pruebas del
    correo de laboratorio y del código del portal pasaron a recorrer el camino
    contrario sin que el nombre de ninguna cambiara.
    """
    settings.EMAIL_BACKEND = LOCMEM

    assert hay_correo_real() is True


def test_smtp_con_servidor_si_envia(settings):
    settings.EMAIL_BACKEND = SMTP
    settings.EMAIL_HOST = "smtp.unl.edu.ec"

    assert hay_correo_real() is True


def test_smtp_sin_servidor_no_envia(settings):
    """`EMAIL_HOST` vacío con backend SMTP ya lo reporta sibu.E041."""
    settings.EMAIL_BACKEND = SMTP
    settings.EMAIL_HOST = ""

    assert hay_correo_real() is False


def test_un_backend_de_un_tercero_se_da_por_bueno(settings):
    """
    No se puede saber desde aquí, y suponer que no envía apagaría un correo
    que sí sale.
    """
    settings.EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"

    assert hay_correo_real() is True


# ---------------------------------------------------- resultados de laboratorio


@pytest.fixture
def orden(db):
    from apps.laboratorio import services
    from apps.laboratorio.models import Examen

    est = crear_estructura()
    _, medico = crear_profesional("medico_correo", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567894")
    exp.persona.correo_institucional = "paciente@unl.edu.ec"
    exp.persona.fecha_nacimiento = date(2000, 5, 15)
    exp.persona.save()

    atencion = crear_atencion(exp, est["medicina"], medico)
    examen = Examen.objects.create(codigo="LAB-001", nombre="Biometría hemática")
    return services.crear_orden(atencion, [examen.id])


@pytest.mark.django_db
def test_sin_correo_configurado_los_resultados_no_se_dan_por_enviados(orden, settings):
    """El defecto: `send_mail` no falla y el sistema se lo creía."""
    from apps.laboratorio.notificaciones import enviar_resultados_al_paciente
    from apps.notificaciones.models import Notificacion

    settings.EMAIL_BACKEND = ARCHIVO

    enviado = enviar_resultados_al_paciente(orden)

    assert enviado is False
    aviso = Notificacion.objects.filter(tipo="resultado_sin_correo_configurado").first()
    assert aviso is not None, "tiene que quedar constancia de que hay que entregarlo a mano"
    assert "ventanilla" in aviso.mensaje
    assert not Notificacion.objects.filter(tipo="resultado_enviado").exists()


@pytest.mark.django_db
def test_con_correo_configurado_los_resultados_si_se_envian(orden, settings, monkeypatch):
    """
    Lo que NO se puede romper al arreglar lo anterior. Se finge que hay correo
    real y se usa el backend de memoria para no abrir una conexión: lo que se
    comprueba es la rama, no el transporte.
    """
    from apps.core import correo as modulo_correo
    from apps.laboratorio.notificaciones import enviar_resultados_al_paciente
    from apps.notificaciones.models import Notificacion

    settings.EMAIL_BACKEND = LOCMEM
    monkeypatch.setattr(modulo_correo, "hay_correo_real", lambda: True)

    enviado = enviar_resultados_al_paciente(orden)

    assert enviado is True
    assert Notificacion.objects.filter(tipo="resultado_enviado").exists()
    assert not Notificacion.objects.filter(tipo="resultado_sin_correo_configurado").exists()


# ------------------------------------------------------------------- portal


@pytest.mark.django_db
def test_sin_correo_configurado_el_portal_no_finge_enviar_el_codigo(db, settings):
    """
    El código ES la prueba de identidad del portal. Sin buzón donde llegue, la
    vinculación se para ANTES de crear nada: dejarla creada sería un estudiante
    esperando para siempre un correo escrito en una carpeta.
    """
    from apps.academico.models import DatoAcademico
    from apps.core.models import PeriodoAcademico
    from apps.portal.models import VinculacionPortal
    from apps.portal.services import solicitar_vinculacion
    from apps.usuarios.models import Rol, Usuario

    settings.EMAIL_BACKEND = ARCHIVO
    crear_estructura()
    exp = crear_expediente(cedula="1104567894")
    periodo = PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril-Agosto",
        fecha_inicio=date(2026, 4, 1),
        fecha_fin=date(2026, 8, 31),
        vigente=True,
    )
    DatoAcademico.objects.create(
        persona=exp.persona, periodo=periodo, email_institucional="ana@unl.edu.ec"
    )
    estudiante = Usuario.objects.create_user(
        username="ana_portal", password="clave-larga-12345", rol_principal=Rol.USUARIO_FINAL
    )

    with pytest.raises(ValidationError, match="no tiene correo configurado"):
        solicitar_vinculacion(estudiante, exp.persona.cedula)

    assert not VinculacionPortal.objects.filter(usuario=estudiante).exists()
