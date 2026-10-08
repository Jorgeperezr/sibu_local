"""
Asigna permisos a los grupos de rol de SIBU según la matriz del informe (10.2).

Idempotente: puede ejecutarse tras cada despliegue. Requiere que exista el seed
inicial (grupos de rol) — ver `seed_inicial`.

Uso:  python manage.py configurar_rbac
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from apps.usuarios.models import Rol

# Rol -> lista de (app_label, codename) de permisos base. La lógica fina de
# acceso por servicio/expediente se resuelve en apps.usuarios.rbac; aquí se
# conceden las capacidades CRUD de alto nivel por módulo.
MATRIZ = {
    Rol.ADMIN_GENERAL: "__all__",
    Rol.DIRECTOR: [
        ("expediente", "view_expediente"),
        ("expediente", "view_persona"),
        ("reportes", "view_reportegenerado"),
        ("auditoria", "view_logauditoria"),
    ],
    Rol.COORDINADOR: [
        ("expediente", "view_expediente"),
        ("expediente", "view_persona"),
        ("citas", "view_cita"),
        ("citas", "add_cita"),
        ("citas", "change_cita"),
        ("reportes", "view_reportegenerado"),
    ],
    Rol.PROFESIONAL: [
        ("expediente", "view_expediente"),
        ("expediente", "view_persona"),
        ("expediente", "add_atencion"),
        ("expediente", "change_atencion"),
        ("expediente", "view_atencion"),
        ("citas", "view_cita"),
    ],
    Rol.LABORATORIO: [
        ("laboratorio", "view_ordenlaboratorio"),
        ("laboratorio", "change_ordenlaboratorio"),
        ("laboratorio", "add_resultadoparametro"),
    ],
    Rol.FARMACIA: [
        ("farmacia", "view_receta"),
        ("farmacia", "add_dispensacion"),
        ("farmacia", "view_medicamento"),
        ("farmacia", "change_lote"),
    ],
    Rol.ADMINISTRATIVO: [
        ("expediente", "view_persona"),
        ("citas", "add_cita"),
        ("citas", "change_cita"),
        ("citas", "view_cita"),
    ],
    Rol.CONSULTA: [
        ("reportes", "view_reportegenerado"),
    ],
    Rol.USUARIO_FINAL: [],
}


class Command(BaseCommand):
    help = "Configura los permisos de los grupos de rol (matriz RBAC del informe)."

    def handle(self, *args, **options):
        for rol, permisos in MATRIZ.items():
            group, _ = Group.objects.get_or_create(name=dict(Rol.choices)[rol])
            if permisos == "__all__":
                group.permissions.set(Permission.objects.all())
                self.stdout.write(f"  {group.name}: todos los permisos")
                continue
            objetos = []
            for app_label, codename in permisos:
                perm = Permission.objects.filter(
                    content_type__app_label=app_label, codename=codename
                ).first()
                if perm:
                    objetos.append(perm)
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  permiso no encontrado: {app_label}.{codename}")
                    )
            group.permissions.set(objetos)
            self.stdout.write(f"  {group.name}: {len(objetos)} permisos")
        self.stdout.write(self.style.SUCCESS("RBAC configurado."))
