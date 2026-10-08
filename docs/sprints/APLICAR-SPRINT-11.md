# Aplicar el Sprint 11

Requiere el fix 10c ya en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/11-arranque

tar -xzf sibu_sprint11_arranque.tar.gz
rm sibu_sprint11_arranque.tar.gz

git status --short   # NINGÚN .tar.gz

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 294 passed
python manage.py check

git add -A
git commit -m "feat: sprint 11 — simplificar el arranque (make up, perfil_dev)"
git push -u origin sprint/11-arranque

git checkout main
git merge --no-ff sprint/11-arranque -m "Merge sprint 11"
git push origin main
```

## Probarlo de inmediato

```bash
make perfil     # asigna tu perfil de dev con los 9 servicios
make up         # levanta la web con las variables ya derivadas
```

Abre la URL que imprime `make up`, o el puerto 8000 en la pestaña Ports.
