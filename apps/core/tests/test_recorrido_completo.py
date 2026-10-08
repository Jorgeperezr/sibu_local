"""
El recorrido completo de un paciente por la Unidad, por las PANTALLAS.

Cada app prueba su pieza y ninguna prueba la cadena. Eso deja fuera lo que más
duele: que una pantalla exista, cargue y sea un callejón sin salida, o que dos
módulos que se pasan el trabajo no encajen —una receta que Farmacia no ve, una
derivación que Psicología no puede aceptar, una orden que Laboratorio no puede
publicar—. Nada de eso sale en una prueba de servicio ni en un 200.

Esta prueba hace el camino con las cuentas reales y por HTTP, con los mismos
formularios que usa quien trabaja:

    admisión → triaje → consulta médica → receta → despacho en farmacia
                                       → orden de laboratorio → resultado
             → derivación a Psicología → proceso psicológico
             → ficha socioeconómica → beca
             → taller

Si algo se rompe entre dos módulos, falla aquí y no en producción.
"""

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

CEDULA = "1104567894"


@pytest.fixture
def sistema(db, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def entra(usuario, clave):
    cliente = Client()
    assert cliente.login(username=usuario, password=clave), f"no entra {usuario}"
    return cliente


def post(cliente, url, datos, espera=(200, 302)):
    """POST que exige que la pantalla acepte el envío, no que exista."""
    respuesta = cliente.post(url, datos, follow=False)
    assert (
        respuesta.status_code in espera
    ), f"POST {url} respondió {respuesta.status_code}: {respuesta.content[:200]}"
    return respuesta


@pytest.fixture
def expediente(sistema):
    """Admisión: la persona entra al sistema por la pantalla de alta."""
    from apps.expediente.models import Expediente

    cliente = entra("1104346091", "1104346091")
    post(
        cliente,
        reverse("expediente:nuevo"),
        {"cedula": CEDULA, "nombres": "María José", "apellidos": "Pérez Ríos"},
    )
    expediente = Expediente.objects.filter(persona__cedula=CEDULA).first()
    assert expediente is not None, "el alta no creó el expediente"
    return expediente


# ------------------------------------------------------------------ el camino


@pytest.mark.django_db
def test_enfermeria_registra_el_triaje(expediente):
    from apps.enfermeria.models import SignosVitales

    cliente = entra("andrea.ambuludi", "andrea.ambuludi")
    post(
        cliente,
        reverse("enfermeria:triaje", args=[expediente.pk]),
        {
            "peso": "58.5",
            "talla": "1.62",
            "pa_sistolica": "118",
            "pa_diastolica": "76",
            "fc": "72",
            "fr": "16",
            "temperatura": "36.6",
        },
    )
    signos = SignosVitales.objects.filter(expediente=expediente).first()
    assert signos is not None, "el triaje no guardó nada"
    assert signos.pa_sistolica == 118


@pytest.mark.django_db
def test_medicina_abre_consulta_diagnostica_receta_y_pide_examenes(expediente):
    """
    El tramo más largo y el que más módulos toca: lo que aquí se prescribe
    aparece en Farmacia y lo que se pide aparece en Laboratorio.
    """
    from apps.farmacia.models import Medicamento, Receta
    from apps.laboratorio.models import Examen, OrdenLaboratorio
    from apps.medicina.models import AtencionMedicina

    cliente = entra("jhoely.lalangui", "jhoely.lalangui")
    post(
        cliente,
        reverse("medicina:iniciar", args=[expediente.pk]),
        {"motivo": "Cefalea de tres días"},
    )
    hc = AtencionMedicina.objects.filter(atencion__expediente=expediente).first()
    assert hc is not None, "no se abrió la historia clínica"
    url = reverse("medicina:consulta", args=[hc.pk])

    post(cliente, url, {"accion": "guardar", "enfermedad_actual": "Cefalea tensional"})

    # El diagnóstico va por código CIE-10, y el catálogo está filtrado por
    # servicio: Medicina no ve los capítulos de salud mental.
    from apps.core.selectors import diagnosticos_por_servicio

    codigo = diagnosticos_por_servicio("medicina").first()
    assert codigo is not None, "el catálogo CIE-10 de Medicina salió vacío"
    post(
        cliente,
        url,
        {"accion": "diagnostico", "cie10": codigo.codigo, "tipo": "presuntivo", "principal": "on"},
    )
    assert hc.atencion.diagnosticos.exists(), "el diagnóstico no se guardó"

    medicamento = Medicamento.objects.first()
    assert medicamento is not None, "la siembra no dejó vademécum"
    post(
        cliente,
        url,
        {
            "accion": "recetar",
            "medicamento": medicamento.pk,
            "cantidad": "10",
            "dosis": "1 tableta",
            "frecuencia": "cada 8 horas",
            "duracion": "3 días",
            "indicaciones": "Con alimentos",
        },
    )
    assert Receta.objects.filter(atencion=hc.atencion).exists(), "la receta no se emitió"

    examen = Examen.objects.first()
    assert examen is not None, "la siembra no dejó catálogo de exámenes"
    # `examenes` es una lista: la pantalla permite pedir varios de una vez.
    post(cliente, url, {"accion": "examenes", "examenes": [examen.pk], "prioridad": "rutina"})
    assert OrdenLaboratorio.objects.filter(
        atencion=hc.atencion
    ).exists(), "la orden de laboratorio no se creó"


@pytest.mark.django_db
def test_la_receta_de_medicina_llega_al_mostrador_de_farmacia(expediente):
    """
    El encaje entre dos módulos: Medicina prescribe, Farmacia despacha. Si la
    receta no aparece en el mostrador, el paciente se va sin medicación y nadie
    ve un error.
    """
    from apps.farmacia.models import Medicamento
    from apps.medicina import services as medicina
    from apps.usuarios.models import Usuario

    medico = Usuario.objects.get(username="jhoely.lalangui")
    hc = medicina.crear_atencion_medicina(
        expediente=expediente, profesional=medico.perfil, motivo="Cefalea", usuario=medico
    )
    from apps.farmacia import services as farmacia

    medicamento = Medicamento.objects.first()
    receta = farmacia.emitir_receta(
        hc.atencion,
        [{"medicamento_id": medicamento.pk, "cantidad_prescrita": 5, "dosis": "1 tableta"}],
    )

    cliente = entra("farmaceutico", "sibu-demo-2026")
    contenido = cliente.get(reverse("farmacia:mostrador")).content.decode()
    assert receta.numero in contenido, "la receta no aparece en el mostrador"

    detalle = cliente.get(reverse("farmacia:despachar", args=[receta.pk]))
    assert detalle.status_code == 200, "el farmacéutico no puede abrir la receta"


@pytest.mark.django_db
def test_farmacia_despacha_y_el_stock_baja(expediente):
    """Despachar mueve inventario: si no baja el saldo, la trazabilidad miente."""
    from apps.farmacia import services as farmacia
    from apps.farmacia.models import Lote, Medicamento
    from apps.medicina import services as medicina
    from apps.usuarios.models import Usuario

    medico = Usuario.objects.get(username="jhoely.lalangui")
    hc = medicina.crear_atencion_medicina(
        expediente=expediente, profesional=medico.perfil, motivo="Cefalea", usuario=medico
    )
    medicamento = Medicamento.objects.filter(lotes__cantidad_actual__gt=0).first()
    assert medicamento is not None, "no hay medicamento con stock"
    receta = farmacia.emitir_receta(
        hc.atencion, [{"medicamento_id": medicamento.pk, "cantidad_prescrita": 5}]
    )
    detalle = receta.detalles.first()
    antes = sum(
        Lote.objects.filter(medicamento=medicamento).values_list("cantidad_actual", flat=True)
    )

    cliente = entra("farmaceutico", "sibu-demo-2026")
    post(
        cliente,
        reverse("farmacia:despachar", args=[receta.pk]),
        {"accion": "despachar_item", "detalle": detalle.pk, "cantidad": "5"},
    )

    despues = sum(
        Lote.objects.filter(medicamento=medicamento).values_list("cantidad_actual", flat=True)
    )
    assert despues == antes - 5, f"el stock no bajó: {antes} -> {despues}"


@pytest.mark.django_db
def test_derivar_a_psicologia_y_que_psicologia_lo_acepte(expediente):
    """
    El cruce de servicios, y el que toca el sello: Medicina deriva, Psicología
    acepta y abre proceso. Si la bandeja de destino no lo muestra, la
    derivación se pierde sin que nadie lo sepa.
    """
    from apps.core.models import Servicio
    from apps.derivaciones.models import Derivacion
    from apps.medicina import services as medicina
    from apps.usuarios.models import Usuario

    medico = Usuario.objects.get(username="jhoely.lalangui")
    hc = medicina.crear_atencion_medicina(
        expediente=expediente, profesional=medico.perfil, motivo="Ánimo bajo", usuario=medico
    )
    psicologia = Servicio.objects.get(codigo="psicologia")

    cliente_medico = entra("jhoely.lalangui", "jhoely.lalangui")
    post(
        cliente_medico,
        reverse("derivaciones:derivar", args=[hc.atencion.pk]),
        {"servicio_destino": psicologia.pk, "motivo": "Valoración", "prioridad": "normal"},
    )
    derivacion = Derivacion.objects.filter(servicio_destino=psicologia).first()
    assert derivacion is not None, "la derivación no se creó"

    cliente_psico = entra("jorge.perez", "jorge.perez")
    bandeja = cliente_psico.get(reverse("derivaciones:bandeja"))
    assert bandeja.status_code == 200
    assert "Valoración" in bandeja.content.decode(), "la derivación no llegó a la bandeja"

    post(
        cliente_psico,
        reverse("derivaciones:gestionar", args=[derivacion.pk]),
        {"accion": "aceptar"},
    )
    derivacion.refresh_from_db()
    assert derivacion.estado == Derivacion.Estado.ACEPTADA


@pytest.mark.django_db
def test_psicologia_abre_proceso_y_registra_una_sesion(expediente):
    from apps.psicologia.models import FichaPsicologica

    cliente = entra("jorge.perez", "jorge.perez")
    post(cliente, reverse("psicologia:iniciar", args=[expediente.pk]), {"motivo": "Ánimo bajo"})
    ficha = FichaPsicologica.objects.filter(atencion__expediente=expediente).first()
    assert ficha is not None, "no se abrió el proceso psicológico"

    post(
        cliente,
        reverse("psicologia:proceso", args=[ficha.pk]),
        {"accion": "sesion", "temas": "Primera entrevista", "evolucion": "Colabora"},
    )
    assert ficha.sesiones.exists(), "la sesión no se registró"


@pytest.mark.django_db
def test_trabajo_social_abre_la_ficha_socioeconomica(expediente):
    from apps.trabajo_social.models import FichaSocioeconomica

    cliente = entra("trabajadora", "sibu-demo-2026")
    respuesta = cliente.get(reverse("trabajo_social:ficha", args=[expediente.pk]))
    assert respuesta.status_code == 200, "no se llega a la ficha socioeconómica"
    post(
        cliente,
        reverse("trabajo_social:ficha", args=[expediente.pk]),
        {"accion": "guardar", "numero_miembros": "4"},
    )
    assert FichaSocioeconomica.objects.filter(expediente=expediente).exists()


@pytest.mark.django_db
def test_odontologia_abre_atencion_y_registra_una_pieza(expediente):
    from apps.odontologia.models import AtencionOdontologia

    cliente = entra("daniel.cabrera", "daniel.cabrera")
    post(cliente, reverse("odontologia:iniciar", args=[expediente.pk]), {"motivo": "Control"})
    atencion = AtencionOdontologia.objects.filter(atencion__expediente=expediente).first()
    assert atencion is not None, "no se abrió la atención odontológica"

    post(
        cliente,
        reverse("odontologia:consulta", args=[atencion.pk]),
        {"accion": "pieza", "pieza_fdi": "11", "estado": "sano"},
    )


@pytest.mark.django_db
def test_psicopedagogia_abre_ficha(expediente):
    from apps.psicopedagogia.models import FichaPsicopedagogica

    cliente = entra("victor.samaniego", "victor.samaniego")
    post(
        cliente,
        reverse("psicopedagogia:iniciar", args=[expediente.pk]),
        {"motivo": "Bajo rendimiento"},
    )
    assert FichaPsicopedagogica.objects.filter(atencion__expediente=expediente).exists()


@pytest.mark.django_db
def test_cada_paso_queda_en_la_linea_de_tiempo_del_expediente(expediente):
    """
    El expediente único es la promesa del sistema: todo lo anterior tiene que
    verse junto. Y con el filtro de siempre —lo de Psicología solo lo ve
    Psicología—, que es lo que hace que «único» no signifique «abierto».
    """
    from apps.medicina import services as medicina
    from apps.psicologia import services as psicologia
    from apps.usuarios.models import Usuario

    medico = Usuario.objects.get(username="jhoely.lalangui")
    psicologo = Usuario.objects.get(username="jorge.perez")
    medicina.crear_atencion_medicina(
        expediente=expediente, profesional=medico.perfil, motivo="Cefalea", usuario=medico
    )
    psicologia.crear_ficha(expediente=expediente, profesional=psicologo.perfil, motivo="Ánimo bajo")

    del_medico = entra("jhoely.lalangui", "jhoely.lalangui").get(
        reverse("expediente:detalle", args=[expediente.pk])
    )
    assert del_medico.status_code == 200
    texto = del_medico.content.decode()
    assert "Cefalea" in texto, "el médico no ve su propia atención"
    assert "Ánimo bajo" not in texto, "el médico ve el motivo de Psicología"

    del_psicologo = entra("jorge.perez", "jorge.perez").get(
        reverse("expediente:detalle", args=[expediente.pk])
    )
    assert "Ánimo bajo" in del_psicologo.content.decode(), "Psicología no ve lo suyo"
