# Cómo aplicar el Sprint 5

```bash
cd /workspaces/sibu
git checkout main && git pull origin main
git checkout -b sprint/05-laboratorio

# Arrastra el tar.gz a la raíz, luego:
tar -xzf sibu_sprint5_laboratorio.tar.gz
rm sibu_sprint5_laboratorio.tar.gz

python manage.py migrate
ruff check . && ruff format --check .   # ANTES de commitear (evita romper el CI)
pytest apps -q                          # esperado: 63 passed
python manage.py check

git add -A
git commit -m "feat: sprint 5 — laboratorio (resultados, validación y envío al paciente)"
git push -u origin sprint/05-laboratorio

git checkout main
git merge --no-ff sprint/05-laboratorio -m "Merge sprint 5: laboratorio"
git push origin main
```

## Prueba rápida
1. `/admin/` → Laboratorio → Exámenes → crear "Biometría hemática" y añadir
   parámetros inline (ej. Hemoglobina, g/dL, sexo M, ref 13–17, crítico_min 7).
2. Desde `/medicina/consulta/<id>/` emitir una orden vía API
   (`POST /api/v1/atenciones/medicina/<id>/ordenes-laboratorio/`).
3. `/laboratorio/` → abrir la orden → registrar toma → capturar resultados.
4. Iniciar sesión con **otro** usuario para validar (la segregación de
   funciones bloquea al mismo que registró).
5. Publicar: el correo aparece en la consola del `runserver`.

## Nota sobre la migración
`0003_parametroexamen_and_more.py` está escrita a mano y **recrea**
`ResultadoParametro` (el campo `parametro` pasó de texto libre a FK). Es seguro
en esta fase porque no hay datos de producción. Si ya cargaste resultados de
prueba, se perderán.
