# Aplicar el Sprint 7b

Requiere el Sprint 7 ya mergeado en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/07b-api-ui

tar -xzf sibu_sprint7b_api_ui.tar.gz
rm sibu_sprint7b_api_ui.tar.gz

# Confirmar que la extracción SÍ ocurrió antes de commitear.
# Debe listar los archivos del sprint. Si aparece un .tar.gz o la lista sale
# vacía, el paquete no se extrajo: no continúes, el sprint no está aplicado.
git status --short

# No hay migraciones nuevas: este sprint solo expone lo que ya existía.
python manage.py migrate

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 169 passed
python manage.py check

git add -A
git commit -m "feat: sprint 7b — API REST e interfaz web de los 4 módulos"
git push -u origin sprint/07b-api-ui

git checkout main
git merge --no-ff sprint/07b-api-ui -m "Merge sprint 7b"
git push origin main
```

## Qué mirar

```bash
# El sello, en las tres capas
pytest apps/usuarios/tests/test_sello_psicologia.py -v   # RBAC  (7)
pytest apps/psicologia/tests/test_api_sello.py -v        # API  (10)
pytest apps/psicologia/tests/test_ui_sello.py -v         # web   (8)

# La regresión de odontología
pytest apps/odontologia/tests/test_ui_rbac.py -v         # (2)
```

Pantallas nuevas: `/psicologia/`, `/psicopedagogia/`,
`/trabajo-social/ficha/<expediente_id>/`, `/derivaciones/`.
