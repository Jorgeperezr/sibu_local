from django.contrib import admin

from .models import CIE10, ParametroSistema, PeriodoAcademico, Seccion, Servicio


@admin.register(Seccion)
class SeccionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "activa")
    prepopulated_fields = {"codigo": ("nombre",)}


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "seccion", "permite_talleres", "activo")
    list_filter = ("seccion", "permite_talleres", "activo")
    prepopulated_fields = {"codigo": ("nombre",)}


@admin.register(PeriodoAcademico)
class PeriodoAcademicoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "fecha_inicio", "fecha_fin", "vigente")
    list_filter = ("vigente",)


@admin.register(CIE10)
class CIE10Admin(admin.ModelAdmin):
    list_display = ("codigo", "descripcion", "capitulo")
    search_fields = ("codigo", "descripcion")


@admin.register(ParametroSistema)
class ParametroSistemaAdmin(admin.ModelAdmin):
    list_display = ("clave", "descripcion")
    search_fields = ("clave",)
