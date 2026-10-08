# Cómo aplicar el paquete del Sprint 2

Contiene los archivos nuevos/modificados del Sprint 2 con la misma estructura de
carpetas, para extraerse sobre el proyecto (requiere el Sprint 1 ya aplicado).

```bash
cd /workspaces/sibu
tar -xzf sibu_sprint2_expediente_rbac.tar.gz
rm sibu_sprint2_expediente_rbac.tar.gz

python manage.py migrate            # sin nuevos modelos, por consistencia
python manage.py configurar_rbac    # aplica la matriz de permisos a los grupos
python manage.py check
pytest apps/usuarios apps/expediente -q

git checkout -b sprint/02-expediente-rbac
git add -A
git commit -m "feat(expediente,usuarios): expediente único, RBAC y búsqueda por cédula — Sprint 2"
git push -u origin sprint/02-expediente-rbac
```

Uso: `/expediente/buscar/` para buscar por cédula y abrir el expediente; la
línea de tiempo se filtra automáticamente según el rol del usuario.
