"""
Informe estadístico a medida: qué variables entran, qué anexos se adjuntan y
qué se retira para proteger la identidad.

Tres cosas se prueban aquí y ninguna es cosmética:

1. **Elegir es elegir.** Un informe con dos variables trae dos, y uno al que se
   le quitaron todas trae solo los totales. La diferencia entre «no elegí» y
   «desmarqué todo» tiene que sobrevivir al formulario.
2. **El anexo no puede contradecir al informe.** La suma de la columna de
   atenciones de cada bloque de evidencia es exactamente la cifra que el
   informe reporta para ese valor. Si esto se rompe, el anexo deja de ser
   evidencia y pasa a ser una segunda versión de los hechos.
3. **La identidad va protegida salvo decisión expresa**, y el número de
   expediente cae con la cédula porque se compone con ella.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.expediente.models import Atencion, Persona
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.reportes import anexos, services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil = crear_profesional("medico_medida", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()

    docente = crear_expediente(cedula="1104567894")
    docente.persona.nombres = "Ana"
    docente.persona.apellidos = "Alvarado"
    docente.persona.sexo = "mujer"
    docente.persona.tipo_vinculo = Persona.TipoVinculo.DOCENTE
    docente.persona.telefono = "072570000"
    docente.persona.correo_institucional = "ana.alvarado@unl.edu.ec"
    docente.persona.save()

    estudiante = crear_expediente(cedula="1712345675")
    estudiante.persona.nombres = "Bruno"
    estudiante.persona.apellidos = "Benítez"
    estudiante.persona.sexo = "hombre"
    estudiante.persona.tipo_vinculo = Persona.TipoVinculo.ESTUDIANTE
    estudiante.persona.save()

    # La docente se atiende dos veces; el estudiante, una.
    for exp in (docente, docente, estudiante):
        Atencion.objects.create(
            expediente=exp,
            servicio=est["medicina"],
            profesional=perfil,
            fecha_hora=timezone.now() - timedelta(hours=1),
        )
    return {"est": est, "medico": medico, "docente": docente, "estudiante": estudiante}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# --------------------------------------------------------------- variables


@pytest.mark.django_db
def test_el_estamento_es_una_variable_del_informe(escenario):
    datos = services.informe_estadistico(escenario["est"]["medicina"])
    por_etiqueta = {f["etiqueta"]: f["total"] for f in datos["estamento"]}
    # Dos atenciones de la docente y una del estudiante: se cuenta por atención.
    assert por_etiqueta == {"Docente": 2, "Estudiante": 1}


@pytest.mark.django_db
def test_solo_salen_las_variables_elegidas(escenario):
    datos = services.informe_estadistico(escenario["est"]["medicina"], variables=["sexo", "genero"])
    assert [s["clave"] for s in datos["secciones"]] == ["sexo", "genero"]
    assert "estamento" not in datos


@pytest.mark.django_db
def test_sin_ninguna_variable_quedan_los_totales(escenario):
    """Desmarcar todo no es lo mismo que no elegir: deja el informe en sus totales."""
    datos = services.informe_estadistico(escenario["est"]["medicina"], variables=[])
    assert datos["secciones"] == []
    assert datos["total_atenciones"] == 3
    assert datos["total_pacientes"] == 2


@pytest.mark.django_db
def test_una_variable_inventada_se_ignora(escenario):
    datos = services.informe_estadistico(
        escenario["est"]["medicina"], variables=["sexo", "signo_zodiacal"]
    )
    assert [s["clave"] for s in datos["secciones"]] == ["sexo"]


# ------------------------------------------------------------------- nómina


@pytest.mark.django_db
def test_la_nomina_lista_personas_no_atenciones(escenario):
    nomina = anexos.nomina(escenario["est"]["medicina"])
    assert nomina["total"] == 2  # tres atenciones, dos personas
    columna = nomina["columnas"].index("atenciones")
    assert sorted(f[columna] for f in nomina["filas"]) == [1, 2]


@pytest.mark.django_db
def test_la_nomina_protege_la_identidad_por_omision(escenario):
    """Sin pedir nada, no salen ni cédula, ni teléfono, ni correo, ni expediente."""
    nomina = anexos.nomina(escenario["est"]["medicina"])
    texto = " ".join(str(c) for fila in nomina["filas"] for c in fila)
    assert "1104567894" not in texto
    assert "072570000" not in texto
    assert "ana.alvarado@unl.edu.ec" not in texto
    # El número de expediente se compone como EXP-<cédula>: publicarlo mientras
    # se oculta la cédula sería publicar la cédula.
    assert "EXP-" not in texto
    assert nomina["protegida"] is True


@pytest.mark.django_db
def test_pedir_la_cedula_no_la_saca_si_la_identidad_esta_protegida(escenario):
    nomina = anexos.nomina(
        escenario["est"]["medicina"], columnas=["nombre", "cedula", "expediente"]
    )
    assert "cedula" not in nomina["columnas"]
    assert "expediente" not in nomina["columnas"]
    # Y se dice qué se retiró: una lista recortada en silencio se lee completa.
    assert "Cédula" in nomina["retiradas"]
    assert "N.º de expediente" in nomina["retiradas"]


@pytest.mark.django_db
def test_sin_proteccion_la_cedula_sale_si_se_pide(escenario):
    nomina = anexos.nomina(
        escenario["est"]["medicina"], columnas=["nombre", "cedula"], proteger=False
    )
    texto = " ".join(str(c) for fila in nomina["filas"] for c in fila)
    assert "1104567894" in texto
    assert nomina["retiradas"] == []


@pytest.mark.django_db
def test_cada_fila_lleva_codigo_para_poder_citarla_sin_nombrarla(escenario):
    nomina = anexos.nomina(escenario["est"]["medicina"], columnas=["atenciones"])
    assert nomina["columnas"][0] == "codigo"
    codigos = [f[0] for f in nomina["filas"]]
    assert codigos == ["A-001", "A-002"]


# --------------------------------------------------------------- evidencias


@pytest.mark.django_db
def test_la_evidencia_suma_exactamente_la_cifra_informada(escenario):
    """
    El anexo existe para respaldar el informe: si no cuadra, sobra.

    Se comprueba variable por variable y valor por valor, no en un caso suelto.
    """
    servicio = escenario["est"]["medicina"]
    datos = services.informe_estadistico(servicio)
    grupos = anexos.evidencias(servicio, columnas=["nombre"])

    for grupo in grupos:
        informado = None
        if grupo["variable"] in services.VARIABLES_DE_CATEGORIA:
            for fila in datos[grupo["variable"]]:
                if fila["etiqueta"] == grupo["valor"]:
                    informado = fila["total"]
        else:
            informado = datos[grupo["variable"]]["total"]
        assert informado is not None, f"{grupo['variable']}={grupo['valor']} no está en el informe"
        assert grupo["atenciones"] == informado


@pytest.mark.django_db
def test_la_evidencia_solo_cubre_las_variables_elegidas(escenario):
    grupos = anexos.evidencias(escenario["est"]["medicina"], variables=["estamento"])
    assert {g["variable"] for g in grupos} == {"estamento"}
    assert {g["valor"] for g in grupos} == {"Docente", "Estudiante"}


@pytest.mark.django_db
def test_la_evidencia_lleva_las_atenciones_aunque_no_se_pidan(escenario):
    """Sin esa columna, el anexo listaría personas junto a un número de atenciones."""
    grupos = anexos.evidencias(escenario["est"]["medicina"], columnas=["nombre"])
    assert "atenciones" in grupos[0]["columnas"]


# ----------------------------------------------------------- confidencialidad


@pytest.mark.django_db
def test_psicologia_no_anexa_nomina_ni_evidencias(escenario):
    """El conteo agregado sí se informa; la lista de nombres no sale de la Unidad."""
    psicologia = escenario["est"]["psicologia"]
    with pytest.raises(ValidationError):
        anexos.nomina(psicologia)
    with pytest.raises(ValidationError):
        anexos.evidencias(psicologia)


@pytest.mark.django_db
def test_la_pantalla_de_psicologia_informa_sin_anexos(db):
    """Pedir el anexo por la URL devuelve el informe con un aviso, no un 500."""
    est = crear_estructura()
    psicologo, _ = crear_profesional("psi_medida", est["psicologia"], est["salud"])
    psicologo.set_password(CLAVE)
    psicologo.save()

    respuesta = _cliente(psicologo).get(
        reverse("reportes:informe_servicio"),
        {"servicio": est["psicologia"].pk, "elegir": "1", "anexos": "nomina"},
    )
    assert respuesta.status_code == 200
    contenido = respuesta.content.decode()
    assert "no exporta su historial" in contenido or "confidencial" in contenido


@pytest.mark.django_db
def test_psicologia_no_descarga_la_nomina_en_excel(db):
    est = crear_estructura()
    psicologo, _ = crear_profesional("psi_excel", est["psicologia"], est["salud"])
    psicologo.set_password(CLAVE)
    psicologo.save()

    respuesta = _cliente(psicologo).get(
        reverse("reportes:informe_servicio_xlsx"), {"servicio": est["psicologia"].pk}
    )
    assert respuesta.status_code == 302  # vuelve al informe con el aviso
    assert "spreadsheet" not in respuesta.get("Content-Type", "")


# ------------------------------------------------------------------ pantalla


@pytest.mark.django_db
def test_el_pdf_incluye_la_nomina_pedida_y_queda_auditado(escenario):
    respuesta = _cliente(escenario["medico"]).get(
        reverse("reportes:informe_servicio_pdf"),
        {
            "servicio": escenario["est"]["medicina"].pk,
            "elegir": "1",
            "variables": "estamento",
            "anexos": "nomina",
            "identidad": "mostrar",
            "columnas": ["nombre", "cedula"],
        },
    )
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "application/pdf"

    log = LogAuditoria.objects.filter(entidad="InformeEstadistico").latest("fecha_hora")
    # Qué llevaba el documento: un informe con nómina identificada es una salida
    # de datos personales y tiene que distinguirse de una tabla de porcentajes.
    assert log.detalle["anexos"] == ["nomina"]
    assert log.detalle["identidad_protegida"] is False
    assert log.detalle["variables"] == ["estamento"]


@pytest.mark.django_db
def test_la_nomina_en_excel_se_descarga_con_la_linea_grafica(escenario):
    respuesta = _cliente(escenario["medico"]).get(
        reverse("reportes:informe_servicio_xlsx"),
        {"servicio": escenario["est"]["medicina"].pk},
    )
    assert respuesta.status_code == 200
    assert "spreadsheetml" in respuesta["Content-Type"]
    assert "nomina-medicina" in respuesta["Content-Disposition"]


@pytest.mark.django_db
def test_la_pantalla_ofrece_las_variables_y_las_columnas(escenario):
    contenido = (
        _cliente(escenario["medico"])
        .get(reverse("reportes:informe_servicio"), {"servicio": escenario["est"]["medicina"].pk})
        .content.decode()
    )
    # Lo que se ofrece marcar sale de donde se calcula, no de una lista en el HTML.
    for etiqueta in services.VARIABLES.values():
        assert etiqueta in contenido
    assert "Nómina de personas atendidas" in contenido
    assert 'value="proteger"' in contenido


# ------------------------------------------------------------------ consultas


@pytest.mark.django_db
def test_la_nomina_no_crece_en_consultas_con_mas_personas(escenario):
    """
    Una nómina de 200 personas debe costar lo mismo que una de 3.

    Es el riesgo evidente del anexo: una fila por persona invita a resolver la
    persona, su dato académico y sus etiquetas dentro del bucle, y entonces el
    informe del semestre tumba la pantalla justo cuando hace falta.
    """
    from django.db import connection, reset_queries
    from django.test.utils import CaptureQueriesContext

    servicio = escenario["est"]["medicina"]

    def _consultas():
        reset_queries()
        with CaptureQueriesContext(connection) as capturadas:
            anexos.nomina(servicio)
        return len(capturadas)

    con_dos = _consultas()

    from apps.academico.tests.factories import generar_cedula
    from apps.expediente.tests.factories import crear_expediente as nuevo

    for indice in range(10):
        expediente = nuevo(cedula=generar_cedula(11, 4000000 + indice))
        Atencion.objects.create(
            expediente=expediente,
            servicio=servicio,
            profesional=escenario["medico"].perfil,
            fecha_hora=timezone.now(),
        )
    assert anexos.nomina(servicio)["total"] == 12
    assert _consultas() == con_dos


@pytest.mark.django_db
def test_se_puede_pedir_un_anexo_sin_nombres(escenario):
    """
    El nombre no se retira con la protección —una nómina sin nombres no es una
    nómina—, pero se puede desmarcar: el código correlativo sostiene la fila.
    """
    nomina = anexos.nomina(escenario["est"]["medicina"], columnas=["estamento", "atenciones"])
    assert "nombre" not in nomina["columnas"]
    texto = " ".join(str(c) for fila in nomina["filas"] for c in fila)
    assert "Alvarado" not in texto
    assert "A-001" in texto


@pytest.mark.django_db
def test_la_casilla_pedida_sigue_marcada_aunque_la_columna_no_salga(escenario):
    """Una casilla que se desmarca sola al enviar el formulario parece un fallo."""
    contenido = (
        _cliente(escenario["medico"])
        .get(
            reverse("reportes:informe_servicio"),
            {
                "servicio": escenario["est"]["medicina"].pk,
                "elegir": "1",
                "columnas": ["nombre", "cedula"],
                "anexos": "nomina",
            },
        )
        .content.decode()
    )
    assert 'id="col-cedula" checked' in contenido
    # Y el anexo dice que la columna se retiró, nombrándola.
    assert "Cédula" in contenido


@pytest.mark.django_db
def test_un_anexo_sin_columnas_no_sale_como_una_lista_de_codigos(escenario):
    """
    Desmarcar todas las columnas dejaba el anexo en A-001, A-002, A-003.

    No informa de nada y no se distingue de un anexo bien hecho sobre datos que
    faltan. Se vio en pantalla, no en una prueba: el enlace del PDF y del Excel
    arrastra la elección, así que el archivo entregado salía igual de vacío.
    """
    nomina = anexos.nomina(escenario["est"]["medicina"], columnas=[])
    assert nomina["columnas"] != ["codigo"]
    assert "nombre" in nomina["columnas"]
    assert "atenciones" in nomina["columnas"]


@pytest.mark.django_db
def test_la_pantalla_no_marca_un_anexo_que_no_se_va_a_adjuntar(db):
    """
    Marcada y deshabilitada a la vez se lee como «activo pero intocable», y lo
    que pasa es lo contrario: en un servicio confidencial no se adjunta.
    """
    est = crear_estructura()
    psicologo, _ = crear_profesional("psi_casilla", est["psicologia"], est["salud"])
    psicologo.set_password(CLAVE)
    psicologo.save()

    contenido = (
        _cliente(psicologo)
        .get(
            reverse("reportes:informe_servicio"),
            {"servicio": est["psicologia"].pk, "elegir": "1", "anexos": "nomina"},
        )
        .content.decode()
    )
    marca = contenido.split('id="anexo-nomina"')[1].split(">")[0]
    assert "disabled" in marca
    assert "checked" not in marca


@pytest.mark.django_db
def test_el_mismo_sexo_escrito_distinto_es_una_sola_fila(escenario):
    """
    Cada estamento entrega su propia base y cada archivo escribe a su manera.

    Con las cuatro bases cargadas el informe salía con «F 6, M 6, Mujer 3,
    Hombre 2» —cuatro filas para dos grupos— y así se entregaba a la Dirección.
    Se vio en pantalla, no en una prueba: con una sola base no ocurre.
    """
    servicio = escenario["est"]["medicina"]
    # La misma escritura que traen las bases: la de estudiantes abrevia.
    escenario["docente"].persona.sexo = "Mujer"
    escenario["docente"].persona.save()
    escenario["estudiante"].persona.sexo = "M"
    escenario["estudiante"].persona.save()

    otra = crear_expediente(cedula="1103003008")
    otra.persona.sexo = "F"  # la misma que «Mujer», escrita como en otra base
    otra.persona.save()
    Atencion.objects.create(
        expediente=otra,
        servicio=servicio,
        profesional=escenario["medico"].perfil,
        fecha_hora=timezone.now(),
    )

    datos = services.informe_estadistico(servicio, variables=["sexo"])
    por_etiqueta = {f["etiqueta"]: f["total"] for f in datos["sexo"]}
    assert por_etiqueta == {"Mujer": 3, "Hombre": 1}, por_etiqueta


@pytest.mark.django_db
def test_la_evidencia_sigue_cuadrando_despues_de_agrupar(escenario):
    """
    Agrupar al contar no puede descuadrar el anexo que respalda la cifra.

    Es la razón de que la normalización viva en `etiquetar` y no en la consulta
    del informe: si el anexo agrupara distinto, desmentiría lo que respalda.
    """
    servicio = escenario["est"]["medicina"]
    escenario["docente"].persona.sexo = "F"
    escenario["docente"].persona.save()
    escenario["estudiante"].persona.sexo = "Mujer"
    escenario["estudiante"].persona.save()

    datos = services.informe_estadistico(servicio, variables=["sexo"])
    grupos = anexos.evidencias(servicio, variables=["sexo"], columnas=["nombre"])
    informado = {f["etiqueta"]: f["total"] for f in datos["sexo"]}
    for grupo in grupos:
        assert grupo["atenciones"] == informado[grupo["valor"]]
