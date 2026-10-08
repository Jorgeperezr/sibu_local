"""
Tablero de gestión.

Las pruebas que importan: quién entra, y que los agregados de Psicología no
señalen a nadie.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.reportes import services
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    psico = Servicio.objects.get(codigo="psicologia")
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    _, psicologo = crear_profesional("psicologo", psico, psico.seccion)
    return {"est": est, "psico": psico, "medico": medico, "psicologo": psicologo}


def _atenciones(escenario, servicio, profesional, cedulas):
    for c in cedulas:
        exp = crear_expediente(cedula=c)
        Atencion.objects.create(
            expediente=exp,
            servicio=servicio,
            profesional=profesional,
            fecha_hora=timezone.now(),
        )


def _directivo(rol):
    u = Usuario.objects.create_user(username=f"dir{rol}", password=CLAVE, rol_principal=rol)
    return u


# --------------------------------------------------------------------------
# Supresión: los agregados no señalan a nadie
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_conteo_pequeno_de_psicologia_se_suprime(escenario):
    """
    Un conteo de 2 pacientes en Psicología identifica casi tanto como un
    nombre. Bajo el umbral, se reporta '<5'.
    """
    _atenciones(escenario, escenario["psico"], escenario["psicologo"], ["1100000007", "1700000001"])
    filas = services.atenciones_por_servicio()
    fila = next(f for f in filas if f["servicio"] == escenario["psico"].nombre)
    assert fila["pacientes"] == services.SUPRIMIDO
    # El total también se suprime bajo el umbral. Antes se mostraba, con el
    # argumento de que es demanda y no identidad; pero los pacientes distintos
    # nunca superan al total, así que un total de 2 dice que los pacientes
    # suprimidos son 1 o 2, y el velo no velaba nada.
    assert fila["total"] == services.SUPRIMIDO


@pytest.mark.django_db
def test_conteo_pequeno_de_medicina_no_se_suprime(escenario):
    """La supresión es para servicios confidenciales, no un velo general."""
    _atenciones(
        escenario, escenario["est"]["medicina"], escenario["medico"], ["1100000007", "1700000001"]
    )
    filas = services.atenciones_por_servicio()
    fila = next(f for f in filas if f["servicio"] == escenario["est"]["medicina"].nombre)
    assert fila["pacientes"] == 2


@pytest.mark.django_db
def test_el_tablero_no_contiene_nombres_ni_cedulas(escenario):
    """Cero identidades: se recorre el tablero serializado completo."""
    import json

    exp_cedula = "1100000007"
    _atenciones(escenario, escenario["psico"], escenario["psicologo"], [exp_cedula])
    datos = services.tablero_general()
    volcado = json.dumps(datos, default=str)
    assert exp_cedula not in volcado
    assert "Paciente" not in volcado  # nombre de las personas de factory


# --------------------------------------------------------------------------
# Acceso
# --------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("rol", [Rol.ADMIN_GENERAL, Rol.DIRECTOR, Rol.COORDINADOR])
def test_roles_directivos_entran(escenario, rol):
    _directivo(rol)
    c = Client()
    c.login(username=f"dir{rol}", password=CLAVE)
    assert c.get("/reportes/").status_code == 200


@pytest.mark.django_db
def test_un_profesional_no_entra_al_tablero(escenario):
    u, _ = crear_profesional("med9", escenario["est"]["medicina"], escenario["est"]["salud"])
    u.set_password(CLAVE)
    u.save()
    c = Client()
    c.login(username="med9", password=CLAVE)
    assert c.get("/reportes/").status_code == 403


@pytest.mark.django_db
def test_un_usuario_del_portal_no_entra_al_tablero(escenario):
    Usuario.objects.create_user(username="estu", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    c = Client()
    c.login(username="estu", password=CLAVE)
    assert c.get("/reportes/").status_code == 403


@pytest.mark.django_db
def test_la_exportacion_queda_auditada(escenario):
    from apps.auditoria.models import LogAuditoria

    _directivo(Rol.DIRECTOR)
    c = Client()
    c.login(username=f"dir{Rol.DIRECTOR}", password=CLAVE)
    r = c.get("/reportes/exportar/")
    assert r.status_code == 200
    assert r["Content-Type"] == "text/csv"
    assert LogAuditoria.objects.filter(
        modulo="reportes", accion=LogAuditoria.Accion.EXPORT
    ).exists()


# --------------------------------------------------------------------------
# Indicadores
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_ausentismo_sobre_citas_finalizadas_no_sobre_el_total(escenario):
    """Contra el total (con futuras y canceladas) el indicador mentiría."""
    from apps.citas.models import Cita

    exp = crear_expediente(cedula="1100000007")
    base = timezone.now() - timedelta(days=3)
    for i, estado in enumerate(
        [
            Cita.Estado.ATENDIDA,
            Cita.Estado.ATENDIDA,
            Cita.Estado.NO_ASISTIO,
            Cita.Estado.RESERVADA,
            Cita.Estado.CANCELADA,
        ]
    ):
        Cita.objects.create(
            expediente=exp,
            servicio=escenario["est"]["medicina"],
            profesional=escenario["medico"],
            fecha_hora=base + timedelta(hours=i),
            estado=estado,
        )
    ind = services.citas_indicadores()
    # 1 ausencia de 3 finalizadas = 33.3, no 1 de 5 = 20
    assert ind["ausentismo_pct"] == 33.3


@pytest.mark.django_db
def test_tablero_vacio_no_revienta(escenario):
    datos = services.tablero_general()
    assert datos["citas"]["ausentismo_pct"] is None
    assert datos["psicopedagogia"]["variacion_promedio"] is None
    assert datos["odontologia"]["promedio"] == 0


@pytest.mark.django_db
def test_por_encima_del_umbral_la_demanda_de_psicologia_se_ve_completa(escenario):
    """
    La supresión es para el tramo que identifica, no un velo permanente: la
    Dirección tiene que poder ver cuánta demanda atiende el servicio.
    """
    cedulas = ["1100000007", "1700000001", "1100000015", "1104567894", "1102030408"]
    _atenciones(escenario, escenario["psico"], escenario["psicologo"], cedulas)
    filas = services.atenciones_por_servicio()
    fila = next(f for f in filas if f["servicio"] == escenario["psico"].nombre)
    assert fila["total"] == 5
    assert fila["pacientes"] == 5


@pytest.mark.django_db
def test_el_total_no_permite_deducir_los_pacientes_suprimidos(escenario):
    """
    El caso que motivó el cambio: una sola atención revelaba que el paciente
    suprimido era exactamente uno.
    """
    _atenciones(escenario, escenario["psico"], escenario["psicologo"], ["1100000007"])
    fila = next(
        f for f in services.atenciones_por_servicio() if f["servicio"] == escenario["psico"].nombre
    )
    assert fila["total"] == services.SUPRIMIDO
    assert fila["pacientes"] == services.SUPRIMIDO


@pytest.mark.django_db
def test_una_derivacion_suelta_a_psicologia_no_se_publica(escenario):
    """
    Misma fuga por otra puerta: el tablero de derivaciones contaba por servicio
    destino sin suprimir, y "1 derivación a Psicología" identifica igual que un
    conteo de 1 paciente.
    """
    from apps.derivaciones.models import Derivacion

    exp = crear_expediente(cedula="1100000007")
    origen = Atencion.objects.create(
        expediente=exp,
        servicio=escenario["est"]["medicina"],
        profesional=escenario["medico"],
        fecha_hora=timezone.now(),
    )
    Derivacion.objects.create(
        atencion_origen=origen,
        servicio_destino=escenario["psico"],
        motivo="prueba",
    )
    datos = services.derivaciones_indicadores()
    fila = next(f for f in datos["por_destino"] if f["destino"] == escenario["psico"].nombre)
    assert fila["total"] == services.SUPRIMIDO


# --------------------------------------------------------------------------
# Reporte en PDF
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_el_reporte_pdf_se_genera_y_queda_auditado(escenario):
    """El documento que se archiva o se entrega, con el membrete institucional."""
    from apps.auditoria.models import LogAuditoria

    _atenciones(escenario, escenario["est"]["medicina"], escenario["medico"], ["1100000007"])
    u = Usuario.objects.create_user(username="dir_pdf", password=CLAVE, rol_principal=Rol.DIRECTOR)
    c = Client()
    c.login(username="dir_pdf", password=CLAVE)

    r = c.get("/reportes/exportar/pdf/")
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")

    log = LogAuditoria.objects.filter(modulo="reportes", entidad_id="pdf").first()
    assert log is not None
    assert log.usuario == u


@pytest.mark.django_db
def test_el_reporte_pdf_no_contiene_identidades(escenario):
    """
    Misma regla que el tablero en pantalla: el documento informa de gestión.

    Un PDF circula más que una pantalla —se adjunta, se imprime, se reenvía—,
    así que la comprobación se hace sobre el texto extraído del documento y no
    solo sobre el HTML.
    """
    pdftotext = pytest.importorskip("pdfminer.high_level", reason="sin extractor de PDF")

    _atenciones(escenario, escenario["psico"], escenario["psicologo"], ["1100000007"])
    Usuario.objects.create_user(username="dir_pdf2", password=CLAVE, rol_principal=Rol.DIRECTOR)
    c = Client()
    c.login(username="dir_pdf2", password=CLAVE)
    r = c.get("/reportes/exportar/pdf/")

    import io

    texto = pdftotext.extract_text(io.BytesIO(r.content))
    assert "1100000007" not in texto
    assert "Paciente" not in texto  # apellido de las personas de factory
    assert services.SUPRIMIDO in texto  # el conteo pequeño va velado


@pytest.mark.django_db
def test_un_profesional_no_descarga_el_reporte(escenario):
    """El tablero, y su PDF, son de la Dirección."""
    lab = Servicio.objects.get(codigo="psicologia")
    u, _ = crear_profesional("psi_pdf", lab, lab.seccion)
    u.set_password(CLAVE)
    u.save()
    c = Client()
    c.login(username="psi_pdf", password=CLAVE)
    assert c.get("/reportes/exportar/pdf/").status_code == 403


@pytest.mark.django_db
def test_el_membrete_nombra_la_unidad_con_la_jerarquia_del_manual(escenario):
    """
    El nombre de la unidad se compone junto al logotipo, con el filete y la
    jerarquía tipográfica que el manual reserva para las dependencias sin
    identificador gráfico propio. No es una línea de texto suelta.
    """
    pdfminer = pytest.importorskip("pdfminer.high_level", reason="sin extractor de PDF")

    Usuario.objects.create_user(username="dir_memb", password=CLAVE, rol_principal=Rol.DIRECTOR)
    c = Client()
    c.login(username="dir_memb", password=CLAVE)

    import io

    texto = pdfminer.extract_text(io.BytesIO(c.get("/reportes/exportar/pdf/").content))
    # Las tres líneas del bloque, cada una por separado.
    assert "Unidad de" in texto
    assert "Bienestar" in texto
    assert "Universitario" in texto
