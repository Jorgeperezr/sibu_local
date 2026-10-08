# Aplicar el Sprint 8c

Requiere el Sprint 8b ya mergeado en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/08c-talleres

tar -xzf sibu_sprint8c_talleres.tar.gz
rm sibu_sprint8c_talleres.tar.gz

git status --short   # debe listar archivos modificados, NINGÚN .tar.gz

python manage.py migrate   # sin migraciones nuevas

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 246 passed
python manage.py check

git add -A
git commit -m "feat: sprint 8c — talleres con almacén intercambiable"
git push -u origin sprint/08c-talleres

git checkout main
git merge --no-ff sprint/08c-talleres -m "Merge sprint 8c"
git push origin main
```

## Qué mirar

```bash
pytest apps/talleres -v   # 25
```

La prueba que más importa: `test_registrar_participante_no_crea_expediente`.

Pantallas nuevas: `/talleres/`, `/talleres/<pk>/`.

## Configuración

**No hace falta configurar nada nuevo.** El almacén local es el defecto.
Requiere `MEDIA_ROOT` definido para adjuntar evidencias.

Para activar Google Drive cuando exista el OAuth institucional:

```bash
TALLERES_ALMACEN=gdrive
GOOGLE_CLIENT_SECRETS=/ruta/al/client_secrets.json
GOOGLE_SHARED_DRIVE_ID=<id del Shared Drive>
```

El cliente de Google Workspace todavía no está integrado: el proveedor lo dice
en vez de fingir que subió el archivo.
