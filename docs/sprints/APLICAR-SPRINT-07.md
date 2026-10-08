# Cómo aplicar el Sprint 7

## ⚠️ ANTES: el fix del CI
Si aún no aplicaste `sibu_fix_ci_ruff_v2.tar.gz` a `main`, hazlo primero.

## Aplicar
```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/07-psicologia-ts-derivaciones

tar -xzf sibu_sprint7_psicologia_ts_derivaciones.tar.gz
rm sibu_sprint7_psicologia_ts_derivaciones.tar.gz

# Confirmar que la extracción SÍ ocurrió antes de commitear.
# Debe listar los archivos del sprint. Si aparece un .tar.gz o la lista sale
# vacía, el paquete no se extrajo: no continúes, el sprint no está aplicado.
git status --short

python manage.py migrate

# SEPARADOS, sin &&
ruff check .
ruff format --check .
pytest apps -q          # esperado: 149 passed
python manage.py check

git add -A
git commit -m "feat: sprint 7 — psicología, psicopedagogía, trabajo social y derivaciones"
git push -u origin sprint/07-psicologia-ts-derivaciones

git checkout main
git merge --no-ff sprint/07-psicologia-ts-derivaciones -m "Merge sprint 7"
git push origin main
```

## Verificar el sello de Psicología
La prueba más importante del sprint:
```bash
pytest apps/usuarios/tests/test_sello_psicologia.py -v
```
Si alguien relaja el RBAC en el futuro, estas 7 pruebas fallan.

## Cargar el catálogo de escalas
`/admin/` → Psicología → Escalas psicométricas → crear PHQ-9:
```json
[
  {"min": 0,  "max": 4,  "etiqueta": "Mínima",          "alerta": false},
  {"min": 5,  "max": 9,  "etiqueta": "Leve",            "alerta": false},
  {"min": 10, "max": 14, "etiqueta": "Moderada",        "alerta": false},
  {"min": 15, "max": 19, "etiqueta": "Moderada-grave",  "alerta": true},
  {"min": 20, "max": 27, "etiqueta": "Grave",           "alerta": true}
]
```
Con `puntaje_min=0` y `puntaje_max=27`. Un PHQ-9 de 22 eleva el riesgo a ALTO
y notifica al coordinador automáticamente.

## Parametrizar el SBU
`/admin/` → Core → Parámetros del sistema → clave `SBU`, valor `470.00`.
Si no existe, el sistema usa 470 por defecto.
