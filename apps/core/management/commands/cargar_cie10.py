"""Carga el catálogo CIE-10 y su correspondencia con los servicios de SIBU."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import CIE10

# Catálogo curado, no el CIE-10 completo (14 000+ códigos): un subconjunto
# real y verificable de diagnósticos frecuentes en atención primaria
# universitaria, organizado por capítulo. Ampliarlo es agregar filas a esta
# lista y volver a correr el comando; es idempotente.
#
# (código, descripción, capítulo)
CATALOGO = [
    # --- Capítulo I: infecciosas y parasitarias ---
    ("A09", "Diarrea y gastroenteritis de presunto origen infeccioso", "I. Infecciosas"),
    ("B34.9", "Infección viral, no especificada", "I. Infecciosas"),
    ("A90", "Fiebre del dengue [dengue clásico]", "I. Infecciosas"),
    # --- Capítulo IV: endocrinas, nutricionales y metabólicas ---
    ("E11", "Diabetes mellitus no insulinodependiente", "IV. Endocrinas"),
    ("E03", "Otros hipotiroidismos", "IV. Endocrinas"),
    ("E66", "Obesidad", "IV. Endocrinas"),
    ("E56", "Deficiencia de otras vitaminas", "IV. Endocrinas"),
    # --- Capítulo V: trastornos mentales y del comportamiento ---
    ("F32", "Episodio depresivo", "V. Salud mental"),
    ("F41", "Otros trastornos de ansiedad", "V. Salud mental"),
    ("F43", "Reacción a estrés grave y trastornos de adaptación", "V. Salud mental"),
    ("F10", "Trastornos mentales y del comportamiento por uso de alcohol", "V. Salud mental"),
    ("F17", "Trastornos mentales y del comportamiento por uso de tabaco", "V. Salud mental"),
    ("F51", "Trastornos no orgánicos del sueño", "V. Salud mental"),
    (
        "F80",
        "Trastornos específicos del desarrollo del habla y del lenguaje",
        "V. Psicopedagógico",
    ),
    (
        "F81",
        "Trastornos específicos del desarrollo del aprendizaje escolar",
        "V. Psicopedagógico",
    ),
    ("F84", "Trastornos generalizados del desarrollo", "V. Psicopedagógico"),
    ("F90", "Trastornos hipercinéticos", "V. Psicopedagógico"),
    (
        "F98",
        "Otros trastornos del comportamiento y de las emociones de comienzo habitual "
        "en la infancia y la adolescencia",
        "V. Psicopedagógico",
    ),
    # --- Capítulo VI: sistema nervioso ---
    ("G43", "Migraña", "VI. Sistema nervioso"),
    ("G47", "Trastornos del sueño", "VI. Sistema nervioso"),
    # --- Capítulo IX: sistema circulatorio ---
    ("I10", "Hipertensión esencial (primaria)", "IX. Circulatorio"),
    # --- Capítulo X: sistema respiratorio ---
    ("J00", "Rinofaringitis aguda [resfriado común]", "X. Respiratorio"),
    ("J02", "Faringitis aguda", "X. Respiratorio"),
    ("J03", "Amigdalitis aguda", "X. Respiratorio"),
    (
        "J06",
        "Infecciones agudas de las vías respiratorias superiores, sitio no especificado",
        "X. Respiratorio",
    ),
    ("J18", "Neumonía, organismo no especificado", "X. Respiratorio"),
    ("J45", "Asma", "X. Respiratorio"),
    # --- Capítulo XI: sistema digestivo (general) ---
    ("K21", "Enfermedad del reflujo gastroesofágico", "XI. Digestivo"),
    ("K29", "Gastritis y duodenitis", "XI. Digestivo"),
    ("K59", "Otros trastornos funcionales del intestino", "XI. Digestivo"),
    # --- Capítulo XI: cavidad bucal, glándulas salivales y maxilares ---
    ("K02", "Caries dental", "XI. Odontología"),
    ("K04", "Enfermedades de la pulpa y de los tejidos periapicales", "XI. Odontología"),
    ("K05", "Gingivitis y enfermedades periodontales", "XI. Odontología"),
    ("K06", "Otros trastornos de la encía y de la zona edéntula", "XI. Odontología"),
    ("K07", "Anomalías dentofaciales [incluso la maloclusión]", "XI. Odontología"),
    ("K08", "Otros trastornos de los dientes y de sus estructuras de sostén", "XI. Odontología"),
    ("K12", "Estomatitis y lesiones afines", "XI. Odontología"),
    ("K13", "Otras enfermedades del labio y de la mucosa oral", "XI. Odontología"),
    # --- Capítulo XIII: sistema osteomuscular ---
    ("M54", "Dorsalgia", "XIII. Osteomuscular"),
    ("M25", "Otros trastornos articulares, no clasificados en otra parte", "XIII. Osteomuscular"),
    # --- Capítulo XIV: sistema genitourinario ---
    ("N30", "Cistitis", "XIV. Genitourinario"),
    ("N39", "Otros trastornos del sistema urinario", "XIV. Genitourinario"),
    (
        "N94",
        "Dolor y otras afecciones asociados con los órganos genitales "
        "femeninos y el ciclo menstrual",
        "XIV. Genitourinario",
    ),
    # --- Capítulo XVIII: síntomas y signos ---
    ("R51", "Cefalea", "XVIII. Síntomas y signos"),
    ("R10", "Dolor abdominal y pélvico", "XVIII. Síntomas y signos"),
    ("R50", "Fiebre de origen desconocido", "XVIII. Síntomas y signos"),
    # --- Capítulo XIX: traumatismos ---
    ("T14", "Traumatismo de región no especificada del cuerpo", "XIX. Traumatismos"),
    # --- Capítulo XXI: factores que influyen en el estado de salud ---
    (
        "Z00",
        "Examen general e investigación de personas sin quejas o sin " "diagnóstico reportado",
        "XXI. Factores de salud",
    ),
    ("Z30", "Atención para la anticoncepción", "XXI. Factores de salud"),
    ("Z34", "Supervisión de embarazo normal", "XXI. Factores de salud"),
    ("Z39", "Atención y examen posparto", "XXI. Factores de salud"),
    ("Z55", "Problemas relacionados con la educación y la alfabetización", "XXI. Trabajo social"),
    (
        "Z59",
        "Problemas relacionados con la vivienda y las circunstancias económicas",
        "XXI. Trabajo social",
    ),
    (
        "Z63",
        "Otros problemas relacionados con el grupo primario de apoyo, "
        "incluso circunstancias familiares",
        "XXI. Trabajo social",
    ),
    ("Z65", "Problemas relacionados con otras circunstancias psicosociales", "XXI. Trabajo social"),
    (
        "Z71",
        "Personas en contacto con los servicios de salud por otras " "consultas y consejo médico",
        "XXI. Factores de salud",
    ),
]


class Command(BaseCommand):
    help = "Carga el catálogo CIE-10 curado de SIBU (idempotente)."

    @transaction.atomic
    def handle(self, *args, **options):
        creados = actualizados = 0
        for codigo, descripcion, capitulo in CATALOGO:
            _, creado = CIE10.objects.update_or_create(
                codigo=codigo, defaults={"descripcion": descripcion, "capitulo": capitulo}
            )
            creados += 1 if creado else 0
            actualizados += 0 if creado else 1
        self.stdout.write(
            self.style.SUCCESS(
                f"CIE-10: {creados} códigos nuevos, {actualizados} actualizados "
                f"({len(CATALOGO)} en total)."
            )
        )
