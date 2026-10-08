# Cómo aplicar el paquete del Sprint 1 en tu Codespace

Este `.tar.gz` contiene solo los archivos nuevos/modificados del Sprint 1,
con la MISMA estructura de carpetas del proyecto, para extraerse encima.

1. Arrastra `sibu_sprint1_academico.tar.gz` a la raíz del proyecto en VS Code.
2. En la terminal del Codespace:

   ```bash
   cd /workspaces/sibu
   tar -xzf sibu_sprint1_academico.tar.gz     # extrae sobre las carpetas existentes
   rm sibu_sprint1_academico.tar.gz

   # Dependencias nuevas del sprint (lectura de Excel/CSV)
   pip install pandas openpyxl

   # Sin migraciones nuevas de modelos, pero por si acaso:
   python manage.py makemigrations
   python manage.py migrate
   python manage.py check
   pytest apps/academico -q
   ```

3. Commit del sprint:

   ```bash
   git checkout -b sprint/01-academico
   git add -A
   git commit -m "feat(academico): carga de ficha socioeconómica (Excel/CSV) — Sprint 1"
   git push -u origin sprint/01-academico
   ```

   Luego abre un Pull Request de `sprint/01-academico` hacia `main` (o `develop`).

4. Uso:
   - Web: `/academico/carga/asistente/` (requiere iniciar sesión como administrador).
   - Consola: `python manage.py cargar_ficha archivo.xlsx --periodo 2026-1`.
