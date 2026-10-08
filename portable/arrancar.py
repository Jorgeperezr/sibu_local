#!/usr/bin/env python3
"""
SIBU portable: lo que hay detrás del icono.

Pulsar el icono tiene que hacer una sola cosa visible —abrirse el navegador en
la pantalla de credenciales— y por debajo hace cuatro:

1. Prepara la carpeta la primera vez (migraciones, servicios, roles, catálogos).
2. Elige un puerto libre del propio computador.
3. Levanta el servidor ahí, en segundo plano.
4. Abre el navegador y espera. Cerrar la ventana cierra el sistema.

Se usa `waitress` y no `gunicorn`: gunicorn no funciona en Windows, y la
portable es sobre todo para Windows.

    python portable/arrancar.py
    python portable/arrancar.py --puerto 8800   # si se quiere uno fijo
    python portable/arrancar.py --sin-navegador # para dejarlo corriendo
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ANFITRION = "127.0.0.1"

# Si la carpeta trae este archivo con una dirección dentro, la portable NO
# levanta su propio servidor: abre el navegador contra el servidor de la
# Unidad. El mismo paquete y el mismo icono sirven para los dos modos, que es
# lo que hace viable la arquitectura de `docs/CONEXION_ENTRE_PORTABLES.md`
# —una sola instancia con los datos, portables como clientes— sin repartir un
# segundo instalador.
ARCHIVO_SERVIDOR = RAIZ / "portable" / "servidor.txt"


def servidor_central() -> str | None:
    """La dirección del servidor de la Unidad, si esta carpeta es un cliente."""
    if not ARCHIVO_SERVIDOR.exists():
        return None
    direccion = ARCHIVO_SERVIDOR.read_text(encoding="utf-8").strip()
    return direccion or None


def puerto_libre(preferido: int | None = None) -> int:
    """
    Un puerto que nadie esté usando.

    Con uno fijo, la segunda vez que alguien abre el programa sin haber cerrado
    la primera recibe «address already in use» y no entiende por qué. Se pide
    al sistema operativo que elija, salvo que se indique uno.
    """
    if preferido:
        return preferido
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((ANFITRION, 0))
        return s.getsockname()[1]


def preparar_django(puerto: int) -> None:
    """
    Deja Django listo para arrancar.

    El origen se fija ANTES de importar los ajustes: `CSRF_TRUSTED_ORIGINS` se
    evalúa al cargarlos, y añadirlo después no tendría efecto. Sin él, el
    sistema levanta, todas las páginas responden y el formulario de acceso
    devuelve 403 — el sitio en pie con todo el mundo fuera.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.portable")
    os.environ["SIBU_ORIGENES"] = f"http://{ANFITRION}:{puerto},http://localhost:{puerto}"

    import django

    django.setup()


def preparar_carpeta(detallado: bool) -> None:
    """
    La primera vez: migraciones, servicios, roles y catálogo CIE-10.

    Es idempotente —`preparar --si-cambio` compara lo que hay con lo que el
    código define—, así que corre en cada arranque y no cuesta nada cuando no
    hay nada que hacer. Hacerlo aquí y no pedirle al profesional que ejecute un
    comando es la diferencia entre una portable y un proyecto de Django.
    """
    from django.core.management import call_command

    verbosidad = 1 if detallado else 0
    call_command("migrate", interactive=False, verbosity=verbosidad)
    call_command("preparar", "--si-cambio", "--sin-demo", verbosity=verbosidad)
    call_command("collectstatic", interactive=False, verbosity=0)


def hay_cuentas() -> bool:
    """
    ¿Hay alguna cuenta de persona?

    No vale `Usuario.objects.exists()`: la migración de django-guardian deja su
    fila `AnonymousUser` y eso siempre es cierto, así que el aviso de «no hay
    ninguna cuenta todavía» no habría salido nunca.
    """
    from apps.usuarios.selectors import cuentas_de_persona

    return cuentas_de_persona().exists()


def abrir_navegador(url: str) -> None:
    """
    Abre el navegador cuando el servidor ya responde.

    Abrirlo antes enseña un «no se puede conectar», y quien lo ve recarga a
    mano o cierra el programa pensando que no funciona.
    """

    def esperar_y_abrir():
        for _ in range(100):  # 10 s de margen
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((ANFITRION, int(url.rsplit(":", 1)[1].split("/")[0]))) == 0:
                    break
            time.sleep(0.1)
        webbrowser.open(url)

    threading.Thread(target=esperar_y_abrir, daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Arranca SIBU portable.")
    parser.add_argument("--puerto", type=int, default=None, help="Puerto fijo.")
    parser.add_argument("--sin-navegador", action="store_true", help="No abrir el navegador.")
    parser.add_argument("--detallado", action="store_true", help="Enseñar lo que hace al preparar.")
    parser.add_argument("--servidor", default=None, help="Abrir contra el servidor de la Unidad.")
    opciones = parser.parse_args()

    central = opciones.servidor or servidor_central()
    if central:
        # Modo cliente: no hay base local que preparar ni servidor que levantar.
        print("SIBU — Unidad de Bienestar Universitario · UNL")
        print(f"Abriendo el sistema de la Unidad: {central}")
        print()
        print("Esta carpeta es un cliente: los datos están en el servidor, no aquí.")
        if not opciones.sin_navegador:
            webbrowser.open(central)
        return 0

    puerto = puerto_libre(opciones.puerto)
    preparar_django(puerto)

    print("SIBU — Unidad de Bienestar Universitario · UNL")
    print("Preparando la carpeta…")
    preparar_carpeta(opciones.detallado)

    url = f"http://{ANFITRION}:{puerto}/"
    if not hay_cuentas():
        # Sin ninguna cuenta, el sistema levanta y luego rechaza a cualquiera
        # que se escriba. Decirlo aquí evita el «las credenciales no funcionan».
        print()
        print("  No hay ninguna cuenta todavía. Cree la primera con:")
        print("      python portable/crear_cuenta.py")
        print()

    print(f"SIBU está en {url}")
    print("Para cerrarlo, cierre esta ventana o pulse Ctrl+C.")

    if not opciones.sin_navegador:
        abrir_navegador(url)

    from waitress import serve

    from config.wsgi import application

    try:
        serve(application, host=ANFITRION, port=puerto, threads=8)
    except KeyboardInterrupt:
        print("\nSIBU cerrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
