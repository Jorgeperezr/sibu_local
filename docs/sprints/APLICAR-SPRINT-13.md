# Aplicar el Sprint 13

Requiere el Sprint 12 ya en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/13-login

tar -xzf sibu_sprint13_login.tar.gz
rm sibu_sprint13_login.tar.gz

git status --short   # NINGÚN .tar.gz

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 309 passed
python manage.py check

git add -A
git commit -m "fix: sprint 13 — pantalla de inicio de sesión (registration/login.html)"
git push -u origin sprint/13-login

git checkout main
git merge --no-ff sprint/13-login -m "Merge sprint 13"
git push origin main
```

## Verlo

Abre `/cuentas/login/` en una ventana de incógnito (o cierra sesión): antes daba
500, ahora muestra el formulario. Ingresa con tu usuario y caerás en la portada.
