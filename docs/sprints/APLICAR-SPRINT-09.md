# Aplicar el Sprint 9

Requiere el Sprint 8d ya mergeado en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/09-reportes

tar -xzf sibu_sprint9_reportes.tar.gz
rm sibu_sprint9_reportes.tar.gz

git status --short   # debe listar archivos modificados, NINGÚN .tar.gz

python manage.py migrate   # sin migraciones nuevas

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 274 passed
python manage.py check

git add -A
git commit -m "feat: sprint 9 — tablero de gestión"
git push -u origin sprint/09-reportes

git checkout main
git merge --no-ff sprint/09-reportes -m "Merge sprint 9"
git push origin main
```

## Qué mirar

```bash
pytest apps/reportes -v   # 11
```

La prueba que más importa: `test_conteo_pequeno_de_psicologia_se_suprime`.

Pantalla nueva: `/reportes/` (solo Dirección, Coordinación y Administración).
