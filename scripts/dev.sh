#!/usr/bin/env bash
# Arranca SIBU en desarrollo con un solo comando.
#
#   bash scripts/dev.sh          # o:  make up
#
# Hace lo que antes había que recordar a mano: derivar las variables de
# Codespaces, confirmar la base de datos, aplicar migraciones pendientes y
# avisar con claridad si el puerto ya está ocupado.
set -euo pipefail
cd "$(dirname "$0")/.."
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.dev}"

# --- 1. Variables que el entorno necesita, derivadas solas ------------------
# Sin CSRF_TRUSTED_ORIGINS la página carga pero TODOS los formularios fallan
# con un error de CSRF que no explica su causa. Por eso se define aquí y no se
# deja al olvido.
# `localhost:8000` va en la lista incluso dentro de Codespaces, y no sobra: su
# reenvío de puertos presenta ese Origin aunque el navegador muestre el dominio
# *.app.github.dev. Sin él la pantalla de inicio de sesión carga y luego
# responde 403 "La verificación CSRF ha fallado" al enviar el formulario.
LOCALES="https://localhost:8000,http://localhost:8000,https://127.0.0.1:8000,http://127.0.0.1:8000"
if [ -n "${CODESPACE_NAME:-}" ]; then
  DOM="${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  export ALLOWED_HOSTS="localhost,127.0.0.1,${DOM}"
  export CSRF_TRUSTED_ORIGINS="https://${DOM},${LOCALES}"
  URL="https://${DOM}/"
else
  export ALLOWED_HOSTS="localhost,127.0.0.1"
  export CSRF_TRUSTED_ORIGINS="${LOCALES}"
  URL="http://localhost:8000/"
fi

# --- 2. Confirmar la base de datos antes de nada ----------------------------
# En docker-compose, PostgreSQL vive en el contenedor 'db'. Si aún no acepta
# conexiones (arranque en frío), un mensaje claro ahorra descifrar un traceback.
if ! python -c "import django; django.setup(); from django.db import connection; connection.ensure_connection()" 2>/dev/null; then
  echo "ERROR: sin conexión a la base de datos (¿el contenedor 'db' arrancó?)."
  echo "       Pruebe 'Rebuild Container' en VS Code, o espere unos segundos y reintente."
  exit 1
fi
echo "base de datos: OK"

# --- 3. Dejar la base al día -----------------------------------------------
# Un servidor arrancado sobre una base sin preparar levanta bien y luego
# rechaza cualquier usuario que se escriba en la pantalla de inicio de sesión,
# porque no hay ninguna cuenta creada. Ese es el "error al iniciar sesión" que
# no se explica solo.
#
# `--si-cambio` decide por su cuenta: prepara si la base está vacía y también
# si la definición de la siembra cambió desde la última vez —lo que pasa tras
# cada `git pull` que trae cuentas o servicios nuevos—. Antes eso obligaba a
# acordarse de `make demo` a mano, y no acordarse se parecía mucho a "las
# credenciales no funcionan".
python manage.py preparar --si-cambio

# --- 4. ¿Ya hay un servidor escuchando? -------------------------------------
# El "That port is already in use" de Django no dice qué hacer. Esto sí.
if command -v lsof >/dev/null 2>&1 && lsof -ti:8000 >/dev/null 2>&1; then
  echo ""
  echo "El puerto 8000 ya está en uso: probablemente un servidor anterior sigue vivo."
  echo "  - Reutilice la pestaña del navegador que ya tenía abierta, o"
  echo "  - libérelo con:  kill \$(lsof -ti:8000)  y vuelva a ejecutar este script."
  exit 1
fi

echo ""
echo "SIBU en marcha -> ${URL}"
echo ""
echo "  Abra esa URL, o el puerto 8000 en la pestaña PORTS de VS Code."
if [ -n "${CODESPACE_NAME:-}" ]; then
  echo "  Si el navegador muestra 'Not Found' o pide iniciar sesión en GitHub,"
  echo "  ponga el puerto 8000 en Public: pestaña PORTS, clic derecho sobre el"
  echo "  puerto -> Port Visibility -> Public."
fi
echo ""
echo "  Para ver o recordar las credenciales:  make cuentas"
echo ""
exec python manage.py runserver 0.0.0.0:8000
