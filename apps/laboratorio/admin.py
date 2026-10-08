from django.contrib import admin

from .models import (
    Examen,
    OrdenExamen,
    OrdenLaboratorio,
    ParametroExamen,
    ResultadoParametro,
)


class ParametroInline(admin.TabularInline):
    model = ParametroExamen
    extra = 1


@admin.register(Examen)
class ExamenAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "perfil", "activo")
    list_filter = ("perfil", "activo")
    search_fields = ("codigo", "nombre")
    inlines = [ParametroInline]


class OrdenExamenInline(admin.TabularInline):
    model = OrdenExamen
    extra = 0


@admin.register(OrdenLaboratorio)
class OrdenLaboratorioAdmin(admin.ModelAdmin):
    list_display = ("id", "atencion", "prioridad", "estado", "enviado_correo_paciente")
    list_filter = ("estado", "prioridad", "enviado_correo_paciente")
    date_hierarchy = "creado_en"
    inlines = [OrdenExamenInline]


@admin.register(ResultadoParametro)
class ResultadoParametroAdmin(admin.ModelAdmin):
    list_display = ("parametro", "valor", "unidad", "marcador", "registrado_en")
    list_filter = ("marcador",)


admin.site.register(ParametroExamen)
