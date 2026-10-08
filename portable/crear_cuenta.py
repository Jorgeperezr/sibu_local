#!/usr/bin/env python3
"""
Crea la primera cuenta de la portable, o cualquier otra.

Sin ninguna cuenta el sistema levanta y rechaza a quien se escriba, que se
parece mucho a «las credenciales no funcionan». Esto lo resuelve sin abrir una
consola de Django ni recordar el nombre de un comando.

    python portable/crear_cuenta.py
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.portable")
    import django

    django.setup()

    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)

    from apps.usuarios.models import Rol, Usuario
    from apps.usuarios.selectors import cuentas_de_persona

    print("SIBU portable — crear una cuenta")
    print()
    usuario = input("Usuario (cédula o usuario institucional): ").strip()
    if not usuario:
        print("Hace falta un usuario.")
        return 1
    if Usuario.objects.filter(username=usuario).exists():
        print(f"La cuenta «{usuario}» ya existe.")
        return 1

    nombres = input("Nombres: ").strip()
    apellidos = input("Apellidos: ").strip()
    clave = getpass.getpass("Contraseña: ")
    if len(clave) < 8:
        print("La contraseña necesita al menos 8 caracteres.")
        return 1
    if clave != getpass.getpass("Repítala: "):
        print("No coinciden.")
        return 1

    # La PRIMERA cuenta nace administradora; las siguientes, no. Si la primera
    # naciera con «Consulta Restringida» —el valor por omisión del campo—
    # entraría y vería seis módulos de diecisiete, sin nadie que pudiera
    # darle más. Es el mismo criterio que `GestorDeUsuarios.create_superuser`.
    #
    # `Usuario.objects.exists()` NO sirve para preguntarlo: la migración de
    # django-guardian deja su fila `AnonymousUser` y siempre es cierto. Se
    # preguntaba así y la primera cuenta nunca se reconocía como primera.
    primera = not cuentas_de_persona().exists()
    cuenta = Usuario.objects.create_user(
        username=usuario,
        password=clave,
        first_name=nombres,
        last_name=apellidos,
        rol_principal=Rol.ADMIN_GENERAL if primera else Rol.CONSULTA,
    )
    if primera:
        cuenta.is_staff = True
        cuenta.is_superuser = True
        cuenta.save(update_fields=["is_staff", "is_superuser"])

    print()
    print(f"Creada la cuenta «{usuario}».")
    if primera:
        print("Es la primera, así que nace como Administración General:")
        print("desde «Perfiles» puede dar de alta y asignar servicios al resto.")
    else:
        print("Nace con Consulta Restringida. Asígnele servicios desde «Perfiles».")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
