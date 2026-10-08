"""
El comando que revisa la coherencia de lo ya guardado, y lo que encontró.

Las restricciones de base de datos impiden escribir un disparate nuevo, pero no
dicen nada de lo escrito antes de existir ellas. Y hay invariantes que ninguna
restricción puede expresar —el saldo de un lote contra la suma de sus
movimientos cruza dos tablas—.

Nada más ejecutarlo sobre la base sembrada encontró dos defectos reales:

- `datos_demo` no era idempotente en el inventario, aunque su documentación lo
  afirmara. El bucle de siembra atrapaba toda excepción con el comentario «ya
  ingresado», dando por hecho que `ingresar_lote` fallaría si el lote existía.
  No falla: SUMA. Tres siembras dejaban 600 unidades donde se declaraban 200.
- `--limpiar` borraba los movimientos —cuelgan del usuario de demostración, que
  sí se borra— y dejaba los lotes con su saldo. Stock sin bitácora es justo lo
  que la pantalla de inventario existe para impedir.
"""

import pytest
from django.core.management import call_command

CLAVE = "clave-larga-12345"


@pytest.fixture
def sembrado(db, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def _revisar(**opciones):
    """Ejecuta el comando y devuelve (salió_limpio, texto)."""
    import io

    salida = io.StringIO()
    try:
        call_command("revisar_datos", stdout=salida, **opciones)
        return True, salida.getvalue()
    except SystemExit:
        return False, salida.getvalue()


# ------------------------------------------------- lo que el comando detecta


@pytest.mark.django_db
def test_la_base_recien_sembrada_esta_limpia(sembrado):
    """
    La prueba que da sentido a todas las demás: si la siembra dejara
    incoherencias, el comando gritaría siempre y dejaría de leerse.
    """
    limpio, texto = _revisar()
    assert limpio, texto


@pytest.mark.django_db
def test_detecta_un_saldo_que_no_cuadra_con_sus_movimientos(sembrado):
    """
    La comprobación que ninguna restricción puede hacer: cruza dos tablas. Es
    la que delata la lectura-modificación-escritura perdida que se corrigió con
    `select_for_update`.
    """
    from apps.farmacia.models import Lote

    lote = Lote.objects.first()
    lote.cantidad_actual += 50  # como si alguien tocara el saldo por el admin
    lote.save(update_fields=["cantidad_actual"])

    limpio, texto = _revisar(detalle=True)
    assert not limpio
    assert "no cuadra" in texto
    assert str(lote.numero_lote) in texto


@pytest.mark.django_db
def test_detecta_una_atencion_con_tratante_de_otro_servicio(sembrado):
    """
    Lo que `verificar_profesional_del_servicio` impide desde el Sprint 15 y
    que una fila anterior seguiría teniendo. En Psicología es acceso al sello:
    quien consta de tratante puede verla.
    """
    from apps.core.models import Servicio
    from apps.expediente.models import Atencion

    atencion = Atencion.objects.exclude(profesional__isnull=True).first()
    otro = Servicio.objects.exclude(pk=atencion.servicio_id).first()
    Atencion.objects.filter(pk=atencion.pk).update(servicio=otro)

    limpio, texto = _revisar()
    assert not limpio
    assert "tratante de otro servicio" in texto


@pytest.mark.django_db
def test_detecta_dos_fichas_socioeconomicas_vigentes(sembrado):
    """
    De la vigente salen el puntaje y el estrato con los que se da una beca.

    Hoy una `UniqueConstraint` lo hace imposible de escribir, así que esta
    comprobación solo puede disparar en el caso para el que el comando existe:
    una base ANTES de aplicar estas migraciones. El aviso del PR lo dice —«estas
    migraciones fallarán si los datos que ya están en el servidor violan alguna
    regla… dos fichas socioeconómicas vigentes»— y mirarlo antes es más barato
    que ver fallar el despliegue.

    Para probarlo hay que reproducir ese momento: se quita la restricción
    dentro de la transacción de la prueba, que pytest revierte al terminar.
    """
    from django.db import connection

    from apps.expediente.models import Expediente
    from apps.trabajo_social.models import FichaSocioeconomica

    # Es un índice único PARCIAL (`condition=Q(vigente=True)`), no una
    # constraint: Postgres lo materializa como índice y se quita como tal.
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX uniq_ficha_socio_vigente_por_expediente")

    expediente = Expediente.objects.first()
    FichaSocioeconomica.objects.filter(expediente=expediente).delete()
    for version in (1, 2):
        FichaSocioeconomica.objects.create(expediente=expediente, vigente=True, version=version)

    limpio, texto = _revisar()
    assert not limpio
    assert "vigentes" in texto


@pytest.mark.django_db
def test_no_corrige_nada(sembrado):
    """
    Un descuadre puede ser un movimiento perdido o un ajuste sin registrar, y
    cada caso se arregla distinto. Corregirlo por su cuenta convertiría un
    descuadre visible en uno silencioso.
    """
    from apps.farmacia.models import Lote

    lote = Lote.objects.first()
    lote.cantidad_actual += 50
    lote.save(update_fields=["cantidad_actual"])
    antes = lote.cantidad_actual

    _revisar()

    lote.refresh_from_db()
    assert lote.cantidad_actual == antes


# ------------------------------------------ los dos defectos que encontró


@pytest.mark.django_db
def test_sembrar_dos_veces_no_duplica_el_stock(sembrado):
    """
    `datos_demo` se documenta como idempotente y el inventario no lo era:
    `ingresar_lote` no falla cuando el lote ya existe, SUMA. El bucle atrapaba
    toda excepción con el comentario «ya ingresado» y cada siembra añadía otras
    200 unidades.
    """
    from apps.farmacia.models import Lote

    antes = {lote.pk: lote.cantidad_actual for lote in Lote.objects.all()}
    assert antes, "la siembra no dejó lotes"

    call_command("datos_demo", verbosity=0)

    despues = {lote.pk: lote.cantidad_actual for lote in Lote.objects.all()}
    assert despues == antes, "resembrar cambió el stock"


@pytest.mark.django_db
def test_limpiar_no_deja_stock_sin_bitacora(sembrado):
    """
    Los movimientos cuelgan del usuario de demostración, así que `--limpiar`
    se los llevaba y dejaba los lotes con su saldo: stock que existe sin nada
    que explique de dónde salió.
    """
    call_command("datos_demo", "--limpiar", verbosity=0)

    limpio, texto = _revisar(detalle=True)
    assert limpio, texto


def _ficha_con(ingresos: dict):
    """
    Una ficha vigente con esos montos guardados.

    Se crea aquí en vez de tomar una de la siembra: `preparar` no siembra
    fichas socioeconómicas, y una prueba que se apoye en la primera que
    encuentre pasaría sin comprobar nada el día que eso cambie.
    """
    from apps.expediente.models import Expediente
    from apps.trabajo_social.models import FichaSocioeconomica

    expediente = Expediente.objects.first()
    assert expediente is not None, "la siembra no dejó expedientes"
    return FichaSocioeconomica.objects.create(
        expediente=expediente, version=1, vigente=True, ingresos=ingresos, egresos={}
    )


@pytest.mark.django_db
def test_detecta_una_ficha_con_montos_ilegibles(sembrado):
    """
    Arreglar la lectura no arregla lo ya cargado.

    Hasta hoy la carga borraba la coma —«450,50» entraba como 45050— y la suma
    descartaba lo que no supiera leer. Las fichas que entraron así siguen en la
    base y ninguna restricción las delata: hay que ir a buscarlas.
    """
    _ficha_con({"ingreso_padre": "45O,50"})

    limpio, texto = _revisar(detalle=True)
    assert not limpio
    assert "montos que no se pueden leer" in texto
    assert "45O,50" in texto


@pytest.mark.django_db
def test_señala_tambien_el_monto_que_admite_dos_lecturas(sembrado):
    """`1.234` puede ser mil doscientos treinta y cuatro o uno coma 234."""
    _ficha_con({"ingreso_madre": "1.234"})

    limpio, texto = _revisar(detalle=True)
    assert not limpio
    assert "dos lecturas" in texto
