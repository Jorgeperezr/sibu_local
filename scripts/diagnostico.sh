#!/usr/bin/env bash
# Diagnóstico de SIBU: estado del repositorio y de la configuración.
#
#   bash scripts/diagnostico.sh > diagnostico.txt 2>&1
#
# El archivo resultante es texto plano y NO contiene secretos: de las variables
# sensibles solo se informa si están definidas, nunca su valor.

echo "==================== SIBU — DIAGNÓSTICO ===================="
date
echo "python: $(python --version 2>&1)   django: $(python -c 'import django;print(django.get_version())' 2>/dev/null || echo '?')"
echo

echo "---------- 1. REPOSITORIO ----------"
echo "rama: $(git branch --show-current)"
echo "HEAD: $(git log --oneline -1)"
echo "sin commitear: $(git status --short | wc -l) archivo(s)"
echo
echo "-- últimos 15 commits --"
git log --oneline -15
echo
echo "-- ramas locales --"
git branch | sed 's/^/   /'
echo

echo "---------- 2. ¿SE COMMITEÓ ALGÚN TARBALL? ----------"
# Un sprint aplicado commiteando el .tar.gz en lugar de extraerlo PARECE
# aplicado y no lo está.
tarballs=$(git ls-files | grep -E '\.tar\.gz$')
if [ -n "$tarballs" ]; then
  echo "*** SÍ — el paquete se commiteó en vez de extraerse: ***"
  echo "$tarballs" | sed 's/^/   /'
  echo "   -> ese sprint NO está aplicado."
else
  echo "OK: ningún .tar.gz versionado."
fi
echo "gitignore protege: $(grep -c 'tar.gz' .gitignore 2>/dev/null || echo 0) regla(s)"
echo

echo "---------- 3. ¿QUÉ SPRINTS ESTÁN APLICADOS? ----------"
for f in \
  "apps/laboratorio/services.py:S5 laboratorio" \
  "apps/odontologia/services.py:S6 odontología" \
  "apps/usuarios/tests/test_sello_psicologia.py:S7 sello psicología" \
  "apps/usuarios/permissions.py:S7b API+UI" \
  "apps/firma/client.py:S8 FirmaEC" \
  "apps/firma/providers.py:S8b firma intercambiable" \
  "apps/becas/services.py:S8b becas" \
  "apps/talleres/providers.py:S8c talleres" \
  "apps/portal/services.py:S8d portal" \
  "apps/reportes/services.py:S9 tablero" \
  "apps/core/checks.py:S10 checks de despliegue" ; do
  ruta="${f%%:*}"; nombre="${f##*:}"
  [ -f "$ruta" ] && echo "   [x] $nombre" || echo "   [ ] $nombre   <-- FALTA"
done
echo

echo "---------- 4. CALIDAD ----------"
echo "-- ruff check --"; ruff check . 2>&1 | tail -3
echo "-- ruff format --"; ruff format --check . 2>&1 | tail -2
echo "-- bandit --"; bandit -r apps config -ll 2>&1 | grep -E "No issues|Issue:" | head -5
echo

echo "---------- 5. PRUEBAS ----------"
pytest apps -q 2>&1 | tail -5
echo

echo "---------- 6. MIGRACIONES ----------"
python manage.py makemigrations --check --dry-run 2>&1 | tail -3
echo "sin aplicar:"
python manage.py showmigrations 2>/dev/null | grep -c '\[ \]' | sed 's/^/   /'
echo

echo "---------- 7. CONFIGURACIÓN (solo presencia, nunca valores) ----------"
python - <<'PYEOF'
import os
sensibles = [
    "SECRET_KEY", "DATABASE_URL", "EMAIL_HOST_PASSWORD",
    "FIRMAEC_API_KEY", "FIRMAEC_CALLBACK_API_KEY", "SENTRY_DSN",
]
visibles = [
    "DJANGO_SETTINGS_MODULE", "DEBUG", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS",
    "MEDIA_ROOT", "EMAIL_HOST", "FIRMA_PROVIDER", "TALLERES_ALMACEN",
    "FIRMAEC_DESCENTRALIZADO_PROPIO", "FIRMAEC_SERVICIO_URL", "FIRMAEC_SISTEMA",
]
for k in visibles:
    print(f"   {k} = {os.environ.get(k, '(sin definir)')}")
for k in sensibles:
    print(f"   {k}: {'definida' if os.environ.get(k) else 'SIN DEFINIR'}")
PYEOF
echo

echo "---------- 8. CHECKS DE DESPLIEGUE ----------"
mod="${DJANGO_SETTINGS_MODULE:-config.settings.dev}"
echo "settings en uso: $mod"
case "$mod" in
  *prod*)
    python manage.py check --deploy 2>&1 | grep -E "sibu\.[EW][0-9]+|security\.[EW][0-9]+|System check" | head -25
    ;;
  *)
    echo "   Los checks de despliegue solo aplican con config.settings.prod."
    echo "   Bajo '$mod' permanecen en silencio A PROPÓSITO, y los avisos"
    echo "   security.W0xx que Django emite aquí describen la configuración de"
    echo "   desarrollo: son esperados y NO indican un problema."
    echo
    echo "   Para comprobar producción de verdad, con el .env real cargado:"
    echo "     DJANGO_SETTINGS_MODULE=config.settings.prod \\"
    echo "       python manage.py check --deploy"
    ;;
esac
echo
echo "==================== FIN ===================="
