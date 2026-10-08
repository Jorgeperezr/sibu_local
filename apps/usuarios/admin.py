from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import PerfilProfesional, Usuario


class PerfilInline(admin.StackedInline):
    model = PerfilProfesional
    filter_horizontal = ("servicios",)
    can_delete = False


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    inlines = [PerfilInline]
    list_display = ("username", "get_full_name", "cedula", "rol_principal", "is_active")
    list_filter = ("rol_principal", "is_active", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("SIBU", {"fields": ("cedula", "rol_principal", "mfa_habilitado", "telefono")}),
    )
