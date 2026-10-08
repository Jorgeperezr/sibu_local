# Sprint 2 — Expediente único + RBAC + búsqueda por cédula

## Objetivo
Construir la base sobre la que se montan todos los servicios clínicos: el
expediente único de la persona, el control de acceso basado en roles (RBAC) y la
búsqueda/verificación por cédula en la interfaz.

## Alcance entregado
- **Núcleo RBAC** (`apps/usuarios/rbac.py`) que formaliza la matriz del informe
  (sección 10) en reglas evaluables: visibilidad por servicio/sección, exclusión
  del contenido confidencial de Psicología, separación de funciones del
  Administrador y filtrado de líneas de tiempo (`atenciones_visibles`).
- **Break the glass** (`apps/usuarios/services.py`): acceso de emergencia
  justificado que queda registrado en la auditoría con motivo obligatorio.
- **Comando `configurar_rbac`**: asigna a cada grupo de rol sus permisos según la
  matriz (idempotente, ejecutable tras cada despliegue).
- **Servicios del expediente** (`apps/expediente/services.py`): resolución por
  cédula contra la base institucional (o alta como externo), obtención/creación
  del expediente y construcción del `snapshot_academico` que se congela en cada
  atención.
- **Selectors** (`apps/expediente/selectors.py`): línea de tiempo consolidada de
  todos los servicios, filtrada por lo que el rol puede ver.
- **API REST**: `GET /api/v1/personas/<cedula>/` (búsqueda + verificación),
  `GET /api/v1/expedientes/<id>/`, `.../timeline/` y `POST .../break_glass/`.
- **Interfaz web**: `/expediente/buscar/` (con tarjeta de verificación y
  semáforo de matrícula) y `/expediente/<id>/` (encabezado, alertas y timeline).
- **Pruebas** (7): profesional ve solo su servicio, Psicología inaccesible aun
  con break-the-glass, Administrador sin clínico por defecto, coordinador ve su
  sección, resolución por cédula, y auditoría del break-the-glass.

## Criterios de aceptación (cumplidos)
- [x] Un profesional solo ve las atenciones de sus servicios (más las propias).
- [x] El contenido de Psicología nunca es visible por otros, ni con break-glass.
- [x] El Administrador no ve contenido clínico por defecto (separación de funciones).
- [x] Todo acceso de emergencia queda auditado con motivo.
- [x] La búsqueda por cédula resuelve contra la base institucional y abre el expediente.
- [x] `manage.py check` limpio; 17 pruebas en verde (Sprint 1 + 2).

## Cómo probar
```bash
python manage.py migrate
python manage.py seed_inicial
python manage.py configurar_rbac
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
# Ir a /expediente/buscar/  (tras cargar una ficha en el Sprint 1)
pytest apps/usuarios apps/expediente -q
```

## Nota sobre pruebas
Se añadió `--import-mode=importlib` en `pyproject.toml` para permitir módulos de
prueba con el mismo nombre en apps distintas (p. ej. varios `test_carga.py`).
