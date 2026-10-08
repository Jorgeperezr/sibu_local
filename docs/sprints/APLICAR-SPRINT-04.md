# Cómo aplicar el Sprint 4

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/04-medicina-enfermeria

# Arrastra el tar.gz a la raíz, luego:
tar -xzf sibu_sprint4_medicina_enfermeria.tar.gz
rm sibu_sprint4_medicina_enfermeria.tar.gz

python manage.py makemigrations
python manage.py migrate
python manage.py check
pytest apps -q          # esperado: 50 passed

git add -A
git commit -m "feat: sprint 4 — enfermería y medicina (triaje, HC, recetas y órdenes)"
git push -u origin sprint/04-medicina-enfermeria

# Merge a main (sin PR)
git checkout main
git merge --no-ff sprint/04-medicina-enfermeria -m "Merge sprint 4: medicina y enfermería"
git push origin main
```

## Prueba rápida del flujo
1. `/admin/` → crear un CIE-10 (ej. J00), un Medicamento y un Examen.
2. `/expediente/buscar/` → buscar una cédula cargada en el Sprint 1.
3. `/enfermeria/triaje/<expediente_id>/` → registrar signos vitales.
4. `/medicina/iniciar/<expediente_id>/` → abrir consulta: el triaje aparece arriba.
5. Agregar diagnóstico CIE-10 marcando "principal" y cerrar la atención.
