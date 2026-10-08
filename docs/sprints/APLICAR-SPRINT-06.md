# Cómo aplicar el Sprint 6

## ⚠️ ANTES: aplicar el fix del CI

Si aún no lo hiciste, aplica primero `sibu_fix_ci_ruff_v2.tar.gz` a `main`.
Sin él, el CI seguirá en rojo por los 70 errores de ruff de los Sprints 1-4.

**El tarball hay que EXTRAERLO, no commitearlo.** Si el commit del fix aparece
en el historial con un diff que solo agrega el `.tar.gz`, la extracción nunca
ocurrió: el fix no está aplicado y `main` sigue en rojo.

```bash
git checkout main && git pull origin main
tar -xzf sibu_fix_ci_ruff_v2.tar.gz
rm sibu_fix_ci_ruff_v2.tar.gz

git status --short   # debe listar archivos .py modificados, NINGÚN .tar.gz
ruff check .         # debe decir: All checks passed!

git add -A
git commit -m "fix(ci): corregir los 70 errores de ruff de los sprints 1-4"
git push origin main
```

## Aplicar el sprint
```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/06-odontologia-farmacia

# Arrastra el tar.gz a la raíz, luego:
tar -xzf sibu_sprint6_odontologia_farmacia.tar.gz
rm sibu_sprint6_odontologia_farmacia.tar.gz

# Confirmar que la extracción SÍ ocurrió antes de commitear.
# Debe listar los archivos del sprint. Si aparece un .tar.gz o la lista sale
# vacía, el paquete no se extrajo: no continúes, el sprint no está aplicado.
git status --short

python manage.py migrate

# Verificar ANTES de commitear — SEPARADOS, sin &&
ruff check .
ruff format --check .
pytest apps -q          # esperado: 94 passed
python manage.py check

git add -A
git commit -m "feat: sprint 6 — odontología (odontograma, CPO-D) y farmacia (despacho FEFO)"
git push -u origin sprint/06-odontologia-farmacia

git checkout main
git merge --no-ff sprint/06-odontologia-farmacia -m "Merge sprint 6: odontología y farmacia"
git push origin main
```

## Prueba rápida
1. `/admin/` → Odontología → Catálogo de procedimientos → crear:
   - `OD-001` "Obturación con resina", requiere pieza ✓, estado resultante = `obturado`
   - `OD-002` "Profilaxis", requiere pieza ✗
2. `/admin/` → Farmacia → Medicamentos → crear Paracetamol 500 mg, stock mínimo 50.
3. Ingresar dos lotes vía API para ver el FEFO:
   ```bash
   # L-LEJANO caduca en 1 año, L-PRONTO en 30 días
   POST /api/v1/farmacia/lotes/ingresar/
   {"medicamento": 1, "numero_lote": "L-LEJANO", "cantidad": 100, "fecha_caducidad": "2027-07-16"}
   POST /api/v1/farmacia/lotes/ingresar/
   {"medicamento": 1, "numero_lote": "L-PRONTO", "cantidad": 30, "fecha_caducidad": "2026-08-15"}
   ```
4. Emitir receta desde `/medicina/consulta/<id>/` (API) y abrir `/farmacia/`.
5. Despachar 45 unidades: verás que consume **L-PRONTO primero**, aunque
   L-LEJANO se ingresó antes.
6. `/odontologia/consulta/<id>/` — clic en una pieza, marcarla cariada, y luego
   registrar la obturación: el odontograma cambia solo.

## Nota sobre la migración
`odontologia/0002_catalogo_odontograma_procedimientos.py` está escrita a mano y
**recrea** `OdontogramaDetalle` (incorpora `registrado_en` y `estado_codigo`
pasa a tener choices). Seguro en esta fase: no hay datos de producción.
