from django.contrib import admin

from .models import EscalaPsicometrica


@admin.register(EscalaPsicometrica)
class EscalaPsicometricaAdmin(admin.ModelAdmin):
    """
    Solo se administra el CATÁLOGO de escalas.

    Las fichas y sesiones NO se registran en el admin: su contenido está
    sellado y el admin de Django no aplica el RBAC de servicio.
    """

    list_display = ("codigo", "nombre", "puntaje_min", "puntaje_max", "activo")
    list_filter = ("activo",)
    search_fields = ("codigo", "nombre")
