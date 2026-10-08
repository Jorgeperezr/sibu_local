from django.contrib import admin

from .models import AlertaClinica, Atencion, Consentimiento, Expediente, Persona


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("cedula", "apellidos", "nombres", "tipo_vinculo", "correo_institucional")
    list_filter = ("tipo_vinculo",)
    search_fields = ("cedula", "nombres", "apellidos")


@admin.register(Expediente)
class ExpedienteAdmin(admin.ModelAdmin):
    list_display = ("numero_expediente", "persona", "grupo_sanguineo", "fecha_apertura")
    search_fields = ("numero_expediente", "persona__cedula")


@admin.register(Atencion)
class AtencionAdmin(admin.ModelAdmin):
    list_display = ("expediente", "servicio", "profesional", "fecha_hora", "tipo", "estado")
    list_filter = ("servicio", "estado", "tipo")
    date_hierarchy = "fecha_hora"


admin.site.register(AlertaClinica)
admin.site.register(Consentimiento)
