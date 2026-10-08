from django.contrib import admin

from .models import AtencionMedicina, Diagnostico


class DiagnosticoInline(admin.TabularInline):
    model = Diagnostico
    extra = 0
    autocomplete_fields = ["cie10"]


@admin.register(AtencionMedicina)
class AtencionMedicinaAdmin(admin.ModelAdmin):
    list_display = ("atencion", "dias_reposo", "proxima_cita_sugerida")
    search_fields = (
        "atencion__expediente__persona__cedula",
        "atencion__expediente__persona__apellidos",
    )


@admin.register(Diagnostico)
class DiagnosticoAdmin(admin.ModelAdmin):
    list_display = ("atencion", "cie10", "tipo", "condicion", "principal")
    list_filter = ("tipo", "condicion", "principal")
    autocomplete_fields = ["cie10"]
