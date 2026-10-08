from django.contrib import admin

from .models import CargaInstitucional, DatoAcademico


@admin.register(CargaInstitucional)
class CargaInstitucionalAdmin(admin.ModelAdmin):
    list_display = (
        "periodo",
        "nombre_archivo",
        "estado",
        "total_filas",
        "altas",
        "actualizaciones",
        "errores",
        "creado_en",
    )
    list_filter = ("estado", "periodo")
    readonly_fields = ("hash_archivo", "bitacora")


@admin.register(DatoAcademico)
class DatoAcademicoAdmin(admin.ModelAdmin):
    list_display = ("persona", "periodo", "facultad", "carrera", "ciclo", "estado")
    list_filter = ("periodo", "facultad", "modalidad", "jornada")
    search_fields = ("persona__cedula", "persona__nombres", "persona__apellidos")
