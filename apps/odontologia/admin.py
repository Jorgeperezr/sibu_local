from django.contrib import admin

from .models import (
    AtencionOdontologia,
    CatalogoProcedimiento,
    OdontogramaDetalle,
    Procedimiento,
)


@admin.register(CatalogoProcedimiento)
class CatalogoProcedimientoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "requiere_pieza", "estado_resultante", "activo")
    list_filter = ("activo", "requiere_pieza")
    search_fields = ("codigo", "nombre")


class OdontogramaInline(admin.TabularInline):
    model = OdontogramaDetalle
    extra = 0


@admin.register(AtencionOdontologia)
class AtencionOdontologiaAdmin(admin.ModelAdmin):
    list_display = ("atencion", "proxima_cita_sugerida")
    search_fields = ("atencion__expediente__persona__cedula",)


@admin.register(Procedimiento)
class ProcedimientoAdmin(admin.ModelAdmin):
    list_display = ("catalogo", "pieza_fdi", "ejecutado_por", "creado_en")
    list_filter = ("catalogo",)


admin.site.register(OdontogramaDetalle)
