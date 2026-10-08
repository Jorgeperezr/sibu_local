# Aplicar el Sprint 8d

Requiere el Sprint 8c ya mergeado en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/08d-portal

tar -xzf sibu_sprint8d_portal.tar.gz
rm sibu_sprint8d_portal.tar.gz

git status --short   # debe listar archivos modificados, NINGÚN .tar.gz

python manage.py migrate   # 1 migración nueva: portal.0001_initial

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 263 passed
python manage.py check

git add -A
git commit -m "feat: sprint 8d — portal de autogestión"
git push -u origin sprint/08d-portal

git checkout main
git merge --no-ff sprint/08d-portal -m "Merge sprint 8d"
git push origin main
```

## Qué mirar

```bash
pytest apps/portal -v   # 17
```

Las dos pruebas que más importan:
- `test_el_codigo_viaja_al_correo_institucional_no_a_uno_digitado`
- `test_el_portal_no_filtra_el_proceso_psicologico`

Pantallas nuevas: `/portal/`, `/portal/vincular/`, `/portal/citas/`.

## Requisitos operativos

- **SMTP configurado en producción**: la vinculación envía el código por correo
  (en pruebas usa el backend en memoria).
- Cuentas de estudiantes con rol `USUARIO_FINAL` (autoregistro de cuentas queda
  fuera de esta fase: las crea el administrativo o el SSO institucional futuro).
