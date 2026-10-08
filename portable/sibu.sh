#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  SIBU portable — Linux y macOS
#
#  Lo que hay detrás del icono. Dele permiso de ejecución una vez:
#      chmod +x portable/sibu.sh
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x "python/bin/python3" ]; then
  PY="python/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo
  echo "  No se encontró Python, y la carpeta no trae el suyo."
  echo "  Instale Python 3.11 o superior."
  echo
  exit 1
fi

echo "Arrancando SIBU... no cierre esta ventana mientras lo use."
exec "$PY" portable/arrancar.py "$@"
