from django.contrib import admin

from .models import Agenda, BloqueoAgenda, Cita


@admin.register(Agenda)
class AgendaAdmin(admin.ModelAdmin):
    list_display = (
        "profesional",
        "servicio",
        "dia_semana",
        "hora_inicio",
        "hora_fin",
        "duracion_turno_min",
        "activa",
    )
    list_filter = ("servicio", "dia_semana", "activa")


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = ("fecha_hora", "expediente", "servicio", "profesional", "estado", "origen")
    list_filter = ("servicio", "estado", "origen")
    date_hierarchy = "fecha_hora"
    search_fields = ("expediente__persona__cedula", "expediente__persona__apellidos")


admin.site.register(BloqueoAgenda)
