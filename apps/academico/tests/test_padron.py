"""
La base institucional cargada: plantilla, diccionario, padrón y autocompletado.

Antes de esto el archivo se cargaba a ciegas —no había forma de saber qué
encabezados esperaba el sistema— y una vez cargado no había pantalla que
mostrara qué había entrado. Lo que estas pruebas fijan es sobre todo eso: que
la plantilla y el diccionario salgan del mapeo y no de una lista escrita
aparte, que el padrón sea solo para quien administra, y que el autocompletado
no se convierta en un volcado del padrón para cualquier cuenta con sesión.
"""

import csv
import io

import pytest
from django.test import Client
from django.urls import reverse

from apps.academico import mapping, selectors
from apps.academico.models import DatoAcademico
from apps.academico.validators import validar_cedula_ecuatoriana
from apps.core.models import PeriodoAcademico
from apps.expediente.models import Persona
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


def _cuenta(username, rol):
    usuario = Usuario.objects.create_user(username=username, password=CLAVE, rol_principal=rol)
    cliente = Client()
    assert cliente.login(username=username, password=CLAVE)
    return usuario, cliente


@pytest.fixture
def periodo(db):
    return PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril–Agosto 2026",
        fecha_inicio="2026-04-01",
        fecha_fin="2026-08-31",
        vigente=True,
    )


@pytest.fixture
def cargado(periodo):
    """Dos personas con su fila académica, como las dejaría una carga aplicada."""
    datos = [
        ("1104567894", "María José", "Pérez Ríos", "Medicina", "Facultad de la Salud Humana"),
        ("1101002002", "Luis Alberto", "Torres Ochoa", "Computación", "Facultad de Energía"),
    ]
    for cedula, nombres, apellidos, carrera, facultad in datos:
        persona = Persona.objects.create(
            cedula=cedula,
            nombres=nombres,
            apellidos=apellidos,
            tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
            sexo="Mujer",
        )
        DatoAcademico.objects.create(
            persona=persona,
            periodo=periodo,
            carrera=carrera,
            facultad=facultad,
            ciclo="3",
            estado="Matriculado",
        )
    return periodo


# ------------------------------------------------------- plantilla y diccionario


@pytest.mark.django_db
def test_la_plantilla_trae_todas_las_columnas_canonicas_sin_repetir():
    """
    La plantilla se genera del mapeo. Si mañana se añade una columna allí y
    aquí no aparece, es que alguien creó una segunda lista en paralelo.
    """
    filas = list(csv.reader(io.StringIO(selectors.plantilla_csv())))
    encabezados = filas[0]
    assert len(encabezados) == len(set(encabezados)), "hay encabezados repetidos"
    assert set(encabezados) == mapping.columnas_canonicas()


@pytest.mark.django_db
def test_la_plantilla_trae_una_fila_de_ejemplo_con_cedula_valida():
    """
    Una cédula de ejemplo que no pasara el módulo 10 haría que la primera
    prueba de carga de quien use la plantilla fallara sin motivo.
    """
    filas = list(csv.DictReader(io.StringIO(selectors.plantilla_csv())))
    assert len(filas) == 1
    for obligatoria in mapping.COLUMNAS_OBLIGATORIAS:
        assert filas[0][obligatoria], f"la fila de ejemplo no llena {obligatoria}"
    assert validar_cedula_ecuatoriana(filas[0]["cedula"])


@pytest.mark.django_db
def test_el_diccionario_lista_cada_columna_exactamente_una_vez():
    listadas = [c["nombre"] for g in selectors.diccionario() for c in g["columnas"]]
    assert len(listadas) == len(set(listadas))
    assert set(listadas) == mapping.columnas_canonicas()
    assert selectors.total_columnas() == len(listadas)


@pytest.mark.django_db
def test_el_diccionario_marca_las_obligatorias_y_las_que_alertan():
    por_nombre = {c["nombre"]: c for g in selectors.diccionario() for c in g["columnas"]}
    assert por_nombre["cedula"]["obligatoria"] is True
    assert por_nombre["celular"]["obligatoria"] is False
    assert por_nombre["estudiante_gestacion"]["alerta"] is True
    assert por_nombre["celular"]["alerta"] is False


@pytest.mark.django_db
def test_la_plantilla_se_descarga_como_csv(db):
    assert Client().get(reverse("academico:plantilla")).status_code == 302  # sin sesión, al login

    _, cliente = _cuenta("admin_plantilla", Rol.ADMIN_GENERAL)
    respuesta = cliente.get(reverse("academico:plantilla"))
    assert respuesta.status_code == 200
    assert "text/csv" in respuesta["Content-Type"]
    # El nombre lleva el estamento: quien descarga las cuatro plantillas
    # acaba con cuatro archivos en la carpeta de descargas y necesita
    # distinguirlos sin abrirlos.
    assert "plantilla-base-institucional-estudiante.csv" in respuesta["Content-Disposition"]
    # BOM: sin él Excel abre el archivo en Latin-1 y parte las tildes.
    assert respuesta.content.startswith(b"\xef\xbb\xbf")


@pytest.mark.django_db
def test_solo_quien_administra_descarga_la_plantilla_y_ve_el_diccionario(db):
    est = crear_estructura()
    profesional, _ = crear_profesional("medico_padron", est["medicina"], est["salud"])
    profesional.set_password(CLAVE)
    profesional.save()
    cliente = Client()
    assert cliente.login(username="medico_padron", password=CLAVE)
    for nombre in ("academico:plantilla", "academico:diccionario", "academico:padron"):
        assert cliente.get(reverse(nombre)).status_code == 302, nombre


# ------------------------------------------------------------------- el padrón


@pytest.mark.django_db
def test_el_padron_muestra_lo_cargado(cargado):
    _, cliente = _cuenta("admin_padron", Rol.ADMIN_GENERAL)
    contenido = cliente.get(reverse("academico:padron")).content.decode()
    assert "1104567894" in contenido
    assert "Pérez Ríos" in contenido
    assert "Computación" in contenido


@pytest.mark.django_db
def test_el_padron_busca_por_cedula_nombre_facultad_o_carrera(cargado):
    _, cliente = _cuenta("admin_busca", Rol.ADMIN_GENERAL)
    contenido = cliente.get(reverse("academico:padron"), {"q": "Torres"}).content.decode()
    assert "Torres Ochoa" in contenido
    assert "Pérez Ríos" not in contenido

    contenido = cliente.get(reverse("academico:padron"), {"q": "Medicina"}).content.decode()
    assert "Pérez Ríos" in contenido
    assert "Torres Ochoa" not in contenido


@pytest.mark.django_db
def test_el_padron_filtra_por_periodo(cargado):
    otro = PeriodoAcademico.objects.create(
        codigo="2025-2",
        nombre="Octubre–Febrero 2025",
        fecha_inicio="2025-10-01",
        fecha_fin="2026-02-28",
    )
    _, cliente = _cuenta("admin_periodo", Rol.ADMIN_GENERAL)
    contenido = cliente.get(reverse("academico:padron"), {"periodo": otro.pk}).content.decode()
    assert "1104567894" not in contenido


# ------------------------------------------------------------ autocompletado


@pytest.mark.django_db
def test_autocompleta_por_cedula_y_por_nombres(cargado):
    est = crear_estructura()
    usuario, _ = crear_profesional("medico_auto", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_auto", password=CLAVE)

    por_cedula = cliente.get(reverse("academico:autocompletar"), {"q": "110456"}).json()
    assert [r["cedula"] for r in por_cedula["resultados"]] == ["1104567894"]
    assert por_cedula["resultados"][0]["carrera"] == "Medicina"

    por_nombre = cliente.get(reverse("academico:autocompletar"), {"q": "Torres"}).json()
    assert [r["cedula"] for r in por_nombre["resultados"]] == ["1101002002"]


@pytest.mark.django_db
def test_el_autocompletado_calla_con_menos_de_tres_caracteres(cargado):
    est = crear_estructura()
    usuario, _ = crear_profesional("medico_corto", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_corto", password=CLAVE)
    assert cliente.get(reverse("academico:autocompletar"), {"q": "11"}).json()["resultados"] == []


@pytest.mark.django_db
def test_el_autocompletado_no_lo_abre_cualquier_cuenta_con_sesion(cargado):
    """
    Sin este permiso, el autocompletado sería un volcado del padrón —nombre,
    cédula, carrera, correo— accesible a un usuario del portal.
    """
    _, cliente = _cuenta("estudiante_curioso", Rol.USUARIO_FINAL)
    assert cliente.get(reverse("academico:autocompletar"), {"q": "Torres"}).status_code == 403


@pytest.mark.django_db
def test_el_autocompletado_no_dice_que_servicio_atiende_a_nadie(cargado):
    """
    El sello de Psicología: saber que a alguien lo atiende Psicología ya es
    contenido. El autocompletado devuelve matrícula, nada más.
    """
    est = crear_estructura()
    usuario, _ = crear_profesional("medico_sello", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_sello", password=CLAVE)
    resultados = cliente.get(reverse("academico:autocompletar"), {"q": "Torres"}).json()[
        "resultados"
    ]
    prohibidas = {"servicio", "servicios", "atenciones", "diagnostico", "expediente", "alertas"}
    assert not (prohibidas & set(resultados[0]))


@pytest.mark.django_db
def test_el_autocompletado_no_crea_expedientes(cargado):
    """
    A diferencia de la búsqueda por cédula, teclear en una caja no puede
    materializar un expediente: se dispara con cada pulsación.
    """
    from apps.expediente.models import Expediente

    est = crear_estructura()
    usuario, _ = crear_profesional("medico_no_crea", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_no_crea", password=CLAVE)
    antes = Expediente.objects.count()
    cliente.get(reverse("academico:autocompletar"), {"q": "1104567894"})
    assert Expediente.objects.count() == antes


# ------------------------------------------------------------------- orden


@pytest.mark.django_db
def test_ordena_por_facultad_en_los_dos_sentidos(cargado):
    from apps.academico.selectors import padron

    ascendente = [d.facultad for d in padron(orden="facultad")]
    descendente = [d.facultad for d in padron(orden="facultad", descendente=True)]
    assert ascendente == sorted(ascendente)
    assert descendente == sorted(descendente, reverse=True)
    assert ascendente != descendente


@pytest.mark.django_db
def test_ordena_por_carrera_y_por_fecha_de_carga(cargado):
    from apps.academico.selectors import padron

    carreras = [d.carrera for d in padron(orden="carrera")]
    assert carreras == sorted(carreras)

    fechas = [d.cargado_en for d in padron(orden="fecha", descendente=True)]
    assert fechas == sorted(fechas, reverse=True)


@pytest.mark.django_db
def test_una_columna_desconocida_no_se_pasa_a_la_consulta(cargado):
    """
    `order_by()` acepta cualquier cadena, incluida la que recorra una relación
    hasta donde no debería llegarse desde aquí. Lo que no esté en la lista
    blanca se ignora y se cae al orden por defecto.
    """
    from django.core.exceptions import FieldError

    from apps.academico.selectors import ORDEN_POR_DEFECTO, campos_de_orden, padron

    # Determinista: se comprueba lo que se le pasa a `order_by`, no el orden
    # resultante, que con datos iguales podría coincidir por azar.
    assert campos_de_orden("persona__creado_por__password", False) == campos_de_orden(
        ORDEN_POR_DEFECTO, False
    )
    assert campos_de_orden("../../etc/passwd", False) == campos_de_orden(ORDEN_POR_DEFECTO, False)

    # Y que además no reviente al consultarse.
    try:
        list(padron(orden="persona__creado_por__password"))
    except FieldError:  # pragma: no cover - solo si la lista blanca desaparece
        pytest.fail("una columna inventada llegó hasta la consulta")


@pytest.mark.django_db
def test_el_orden_descendente_no_invierte_el_desempate(cargado):
    """
    «Facultad descendente» invierte las facultades, no los nombres dentro de
    cada facultad: no es lo que se pide al pulsar una cabecera.
    """
    from apps.academico.selectors import campos_de_orden

    assert campos_de_orden("facultad", True) == [
        "-facultad",
        "persona__apellidos",
        "persona__nombres",
    ]


@pytest.mark.django_db
def test_la_pantalla_ordena_y_señala_por_donde(cargado):
    _, cliente = _cuenta("admin_orden", Rol.ADMIN_GENERAL)
    respuesta = cliente.get(reverse("academico:padron"), {"orden": "facultad", "dir": "desc"})
    contenido = respuesta.content.decode()
    assert respuesta.context["orden"] == "facultad"
    assert respuesta.context["descendente"] is True
    # La flecha dice cuál manda y hacia dónde: una tabla que se reordena sin
    # decir por qué se lee como un fallo.
    assert "bi-caret-down-fill" in contenido


@pytest.mark.django_db
def test_ordenar_no_pierde_el_filtro(cargado):
    """
    Los enlaces de las cabeceras arrastran la búsqueda: si no, ordenar
    devolvería la tabla completa y el filtro se perdería sin avisar.
    """
    _, cliente = _cuenta("admin_filtro", Rol.ADMIN_GENERAL)
    respuesta = cliente.get(reverse("academico:padron"), {"q": "Torres", "orden": "carrera"})
    contenido = respuesta.content.decode()
    assert "Torres Ochoa" in contenido
    assert "Pérez Ríos" not in contenido
    assert "q=Torres" in contenido  # los enlaces de cabecera lo conservan


# ----------------------------------------------------------------- filtros


@pytest.mark.django_db
def test_filtra_por_columna_exacta(cargado):
    from apps.academico.selectors import padron

    solo_energia = padron(filtros={"facultad": "Facultad de Energía"})
    assert [d.persona.cedula for d in solo_energia] == ["1101002002"]


@pytest.mark.django_db
def test_los_filtros_se_acumulan(cargado):
    """Cada filtro estrecha: dos que no coinciden no devuelven nada."""
    from apps.academico.selectors import padron

    assert padron(filtros={"facultad": "Facultad de Energía", "carrera": "Medicina"}).count() == 0
    assert (
        padron(filtros={"facultad": "Facultad de Energía", "carrera": "Computación"}).count() == 1
    )


@pytest.mark.django_db
def test_un_filtro_inventado_no_llega_a_la_consulta(cargado):
    """
    Lista blanca, igual que el orden: `filter()` acepta cualquier cadena,
    incluida la que recorra una relación hasta donde no debería llegarse.
    """
    from django.core.exceptions import FieldError

    from apps.academico.selectors import padron

    try:
        assert padron(filtros={"persona__creado_por__password": "x"}).count() == 2
    except FieldError:  # pragma: no cover
        pytest.fail("un filtro inventado llegó hasta la consulta")


@pytest.mark.django_db
def test_las_opciones_salen_de_lo_cargado(cargado):
    """
    Un desplegable con facultades que nadie cargó ofrece búsquedas vacías, y
    omite las que sí están porque el archivo traía otro nombre.
    """
    from apps.academico.selectors import opciones_de_filtro

    opciones = opciones_de_filtro()
    assert set(opciones["facultad"]) == {"Facultad de la Salud Humana", "Facultad de Energía"}
    assert set(opciones["carrera"]) == {"Medicina", "Computación"}
    # Sin valores vacíos: no son una opción, son un dato que falta.
    assert "" not in opciones["facultad"]


@pytest.mark.django_db
def test_el_texto_busca_en_todas_las_columnas(cargado):
    """
    Quien busca «Matriculado» o una modalidad no tiene por qué saber en qué
    columna vive esa palabra.
    """
    from apps.academico.selectors import padron

    assert padron("Computación").count() == 1
    assert padron("Matriculado").count() == 2


@pytest.mark.django_db
def test_cada_palabra_estrecha_la_busqueda(cargado):
    """Se exigen TODAS: añadir una palabra no puede ensanchar el resultado."""
    from apps.academico.selectors import padron

    assert padron("Energía").count() == 1
    assert padron("Energía Medicina").count() == 0


@pytest.mark.django_db
def test_la_pantalla_filtra_y_ofrece_quitar_los_filtros(cargado):
    _, cliente = _cuenta("admin_filtros", Rol.ADMIN_GENERAL)
    respuesta = cliente.get(reverse("academico:padron"), {"facultad": "Facultad de Energía"})
    contenido = respuesta.content.decode()
    assert "Torres Ochoa" in contenido
    assert "Pérez Ríos" not in contenido
    assert respuesta.context["activos"] == {"facultad": ["Facultad de Energía"]}
    assert "Quitar filtros" in contenido


@pytest.mark.django_db
def test_ordenar_conserva_los_filtros_de_columna(cargado):
    _, cliente = _cuenta("admin_orden_filtro", Rol.ADMIN_GENERAL)
    respuesta = cliente.get(
        reverse("academico:padron"), {"facultad": "Facultad de Energía", "orden": "carrera"}
    )
    # Los enlaces de las cabeceras arrastran el filtro; si no, ordenar
    # devolvería la tabla entera y el filtro se perdería sin avisar.
    assert "facultad=Facultad" in respuesta.content.decode()


# ------------------------------------------------- varios valores por filtro


@pytest.fixture
def tres_facultades(cargado):
    """Una tercera fila, para que «dos de tres» no sea lo mismo que «todo»."""
    persona = Persona.objects.create(
        cedula="1100000007",
        nombres="Ana Lucía",
        apellidos="Jaramillo Vega",
        tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
    )
    DatoAcademico.objects.create(
        persona=persona,
        periodo=cargado,
        carrera="Derecho",
        facultad="Facultad Jurídica",
        ciclo="1",
        estado="Matriculado",
    )
    return cargado


@pytest.mark.django_db
def test_dos_valores_de_la_misma_columna_son_alternativas(tres_facultades):
    """
    Marcar Energía y Salud Humana debe traer las dos, no cero. Con `filter()`
    encadenado por valor —una llamada por cada uno— la consulta pediría que la
    misma fila tuviera dos facultades a la vez y no devolvería ninguna.
    """
    from apps.academico.selectors import padron

    cedulas = {
        d.persona.cedula
        for d in padron(
            filtros={"facultad": ["Facultad de Energía", "Facultad de la Salud Humana"]}
        )
    }
    assert cedulas == {"1101002002", "1104567894"}


@pytest.mark.django_db
def test_dos_valores_siguen_dejando_fuera_al_tercero(tres_facultades):
    """Que traiga varias no puede degenerar en que las traiga todas."""
    from apps.academico.selectors import padron

    consulta = padron(filtros={"facultad": ["Facultad de Energía", "Facultad de la Salud Humana"]})
    assert consulta.count() == 2
    assert "1100000007" not in {d.persona.cedula for d in consulta}


@pytest.mark.django_db
def test_columnas_distintas_se_siguen_acumulando(tres_facultades):
    """Dentro de una columna, «o»; entre columnas, «y». Las dos a la vez."""
    from apps.academico.selectors import padron

    consulta = padron(
        filtros={
            "facultad": ["Facultad de Energía", "Facultad de la Salud Humana"],
            "carrera": ["Computación"],
        }
    )
    assert [d.persona.cedula for d in consulta] == ["1101002002"]


@pytest.mark.django_db
def test_un_solo_valor_en_texto_sigue_valiendo(tres_facultades):
    """
    Un enlace viejo o una llamada desde código pasa una cadena, no una lista.
    Sin esto, `__in` sobre una cadena la recorrería letra a letra.
    """
    from apps.academico.selectors import padron

    assert [d.persona.cedula for d in padron(filtros={"facultad": "Facultad Jurídica"})] == [
        "1100000007"
    ]


@pytest.mark.django_db
def test_la_pantalla_admite_varios_valores_del_mismo_filtro(tres_facultades):
    _, cliente = _cuenta("admin_multi", Rol.ADMIN_GENERAL)
    respuesta = cliente.get(
        reverse("academico:padron"),
        {"facultad": ["Facultad de Energía", "Facultad de la Salud Humana"]},
    )
    contenido = respuesta.content.decode()
    assert "Torres Ochoa" in contenido
    assert "Pérez Ríos" in contenido
    assert "Jaramillo Vega" not in contenido
    assert respuesta.context["activos"]["facultad"] == [
        "Facultad de Energía",
        "Facultad de la Salud Humana",
    ]


@pytest.mark.django_db
def test_ordenar_arrastra_los_dos_valores_marcados(tres_facultades):
    """
    Lo que se pierde sin `doseq`: la lista se codificaría como una sola cadena
    "['a', 'b']" y al pulsar una cabecera el filtro dejaría de existir.
    """
    _, cliente = _cuenta("admin_multi_orden", Rol.ADMIN_GENERAL)
    respuesta = cliente.get(
        reverse("academico:padron"),
        {"facultad": ["Facultad de Energía", "Facultad de la Salud Humana"]},
    )
    arrastre = respuesta.context["filtros"]
    assert arrastre.count("facultad=") == 2
    assert "%5B" not in arrastre  # ningún "[" codificado: no es una lista impresa


@pytest.mark.django_db
def test_las_casillas_marcadas_se_ven_marcadas_al_volver(tres_facultades):
    """Sin esto la tabla sale filtrada y el panel de filtros aparece en blanco."""
    _, cliente = _cuenta("admin_multi_marcado", Rol.ADMIN_GENERAL)
    contenido = (
        cliente.get(
            reverse("academico:padron"),
            {"facultad": ["Facultad de Energía", "Facultad de la Salud Humana"]},
        )
        .content.decode()
        .replace("\n", " ")
    )
    assert contenido.count("selected") >= 2
    assert "multiple" in contenido
