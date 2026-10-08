# Aplicar el Sprint 12

Requiere el Sprint 11 ya en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/12-navegacion

tar -xzf sibu_sprint12_navegacion.tar.gz
rm sibu_sprint12_navegacion.tar.gz

git status --short   # NINGÚN .tar.gz

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 304 passed
python manage.py check

git add -A
git commit -m "feat: sprint 12 — navegación derivada del RBAC"
git push -u origin sprint/12-navegacion

git checkout main
git merge --no-ff sprint/12-navegacion -m "Merge sprint 12"
git push origin main
```

## Verlo

Con `make up` corriendo y tu perfil asignado (`make perfil` o
`python manage.py perfil_dev --usuario jorgeperez`), abre la portada: ahora
lista los módulos como tarjetas, y la cabecera azul los lleva en un menú. Cada
módulo aparece solo si tu servicio o rol lo permite.
