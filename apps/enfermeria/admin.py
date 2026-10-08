from django.contrib import admin

from .models import AtencionEnfermeria, SignosVitales


@admin.register(SignosVitales)
class SignosVitalesAdmin(admin.ModelAdmin):
    list_display = (
        "expediente",
        "fecha_hora",
        "temperatura",
        "fc",
        "pa_sistolica",
        "pa_diastolica",
        "sat_o2",
        "imc",
        "responsable",
    )
    list_filter = ("responsable",)
    date_hierarchy = "fecha_hora"


@admin.register(AtencionEnfermeria)
class AtencionEnfermeriaAdmin(admin.ModelAdmin):
    list_display = ("atencion", "charla_educativa")
