# Aplicar el Sprint 14

Requiere el Sprint 13 ya en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/14-frontend

tar -xzf sibu_sprint14_frontend.tar.gz
rm sibu_sprint14_frontend.tar.gz

git status --short   # NINGÚN .tar.gz

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 314 passed
python manage.py check

git add -A
git commit -m "feat: sprint 14 — capa visual temporal"
git push -u origin sprint/14-frontend

git checkout main
git merge --no-ff sprint/14-frontend -m "Merge sprint 14"
git push origin main
```

## Verlo

`make up` y recarga. La barra superior pasa a verde, la portada muestra tarjetas
con relieve, las tablas y tarjetas de cada módulo ganan jerarquía, y el 404 del
favicon desaparece. Si el navegador conserva el CSS viejo, fuerza recarga con
Ctrl+Shift+R.
