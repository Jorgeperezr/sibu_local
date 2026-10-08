# Aplicar el Sprint 8b

Requiere el Sprint 8 ya mergeado en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/08b-firma-becas

tar -xzf sibu_sprint8b_firma_becas.tar.gz
rm sibu_sprint8b_firma_becas.tar.gz

git status --short   # debe listar archivos modificados, NINGÚN .tar.gz

python manage.py migrate   # sin migraciones nuevas

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 221 passed
python manage.py check

git add -A
git commit -m "feat: sprint 8b — firma intercambiable y becas fase 1"
git push -u origin sprint/08b-firma-becas

git checkout main
git merge --no-ff sprint/08b-firma-becas -m "Merge sprint 8b"
git push origin main
```

## Qué mirar

```bash
pytest apps/becas -v    # 21 — las reglas que protegen a la persona becada
pytest apps/firma -v    # 31 — la firma como pieza intercambiable
```

Pantallas nuevas: `/becas/`, `/becas/ficha/<pk>/`.

## Configuración

**No hace falta configurar nada nuevo.** La firma viene deshabilitada por
defecto y el sistema funciona: los documentos se generan y se descargan sin
firmar.

Para activar FirmaEC cuando el MINTEL registre a la UNL:

```bash
FIRMA_PROVIDER=firmaec
FIRMAEC_SERVICIO_URL=https://impws.firmadigital.gob.ec/servicio
FIRMAEC_SISTEMA=<el que asigne el MINTEL>
FIRMAEC_API_KEY=<la que entregue el MINTEL>
FIRMAEC_CALLBACK_API_KEY=<generar una y comunicarla>
```
