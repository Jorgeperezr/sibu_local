# Aplicar el Sprint 8

Requiere el Sprint 7b ya mergeado en `main`.

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/08-firma

tar -xzf sibu_sprint8_firma_firmaec.tar.gz
rm sibu_sprint8_firma_firmaec.tar.gz

git status --short   # debe listar archivos modificados, NINGÚN .tar.gz

python manage.py migrate

ruff check .            # SEPARADOS, sin &&
ruff format --check .
pytest apps -q          # esperado: 194 passed
python manage.py check

git add -A
git commit -m "feat: sprint 8 — firma electrónica con FirmaEC"
git push -u origin sprint/08-firma

git checkout main
git merge --no-ff sprint/08-firma -m "Merge sprint 8"
git push origin main
```

## Probar sin FirmaEC registrado

Las pruebas simulan el callback, así que no hace falta infraestructura:

```bash
pytest apps/firma -v            # 25 pruebas
```

## Para probar de extremo a extremo

1. Instalar FirmaEC: https://www.firmadigital.gob.ec/descargar-firmaec/
2. Pedir al MINTEL el alta en **preproducción** (`https://impws.firmadigital.gob.ec`).
3. Configurar en `.env`:
   ```bash
   FIRMAEC_SERVICIO_URL=https://impws.firmadigital.gob.ec/servicio
   FIRMAEC_SISTEMA=<el nombre que asigne el MINTEL>
   FIRMAEC_API_KEY=<la que entregue el MINTEL>
   FIRMAEC_CALLBACK_API_KEY=<generar una y comunicarla>
   FIRMAEC_PREPRODUCCION=True
   ```
4. El callback debe ser **alcanzable desde internet por https**. En Codespaces,
   exponer el puerto como público no basta: FirmaEC exige 443 con subdominio.

## Antes de producción

Ver la sección "Requisitos NO técnicos" de `SPRINT-08-firma-firmaec.md`.
Hace falta el oficio de delegación del AIF y el registro ante el MINTEL.
