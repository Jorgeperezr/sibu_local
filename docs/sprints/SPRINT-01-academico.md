# Sprint 1 — Módulo `academico` (base institucional)

## Objetivo
Cargar la base institucional a partir de la **ficha socioeconómica de matrícula**
(Excel/CSV) que la UNL entrega cada período, dejando lista la consulta por cédula
que alimentará a todos los demás módulos.

## Alcance entregado
- **Mapeo oficial** de ~157 columnas de la ficha a los modelos `Persona`,
  `DatoAcademico`, `Expediente` y a las estructuras JSONB de
  `FichaSocioeconomica` (`apps/academico/mapping.py`).
- **Validadores**: cédula ecuatoriana (módulo 10), correo institucional,
  normalización de cédulas (cero inicial perdido por Excel), fechas y montos
  (`apps/academico/validators.py`).
- **Motor de carga en 6 pasos** con modo previsualización e idempotencia
  (`apps/academico/services.py`): lee → mapea → valida → previsualiza → aplica
  (upsert transaccional) → bitácora.
- **Pre-población automática** de la ficha socioeconómica (origen = matrícula),
  que Trabajo Social luego verifica sin partir de cero.
- **Generación de alertas** hacia las bandejas de Trabajo Social (violencia,
  maltrato), Psicopedagogía (NEE), Medicina (discapacidad, gestación) y
  Psicología (consumo).
- **Interfaces de uso**:
  - Comando: `python manage.py cargar_ficha <archivo> --periodo 2026-1 [--dry-run]`
  - API REST: `POST /api/v1/academico/cargas/`, `.../previsualizar/`, `.../aplicar/`,
    y `GET /api/v1/personas/<cedula>/verificacion/`
  - Asistente web (Bootstrap) en `/academico/carga/asistente/` y enlace desde el admin.
- **Tarea Celery** `aplicar_carga_async` para archivos grandes.
- **Pruebas** (10) que cubren validadores y el flujo completo de carga con un
  Excel sintético (altas, errores, pre-población, alertas, idempotencia, preview).

## Criterios de aceptación (cumplidos)
- [x] Una cédula inválida no detiene la carga: se cuenta como error y se reporta.
- [x] Reejecutar la misma carga no duplica personas ni datos (upsert idempotente).
- [x] La fila cruda completa se conserva en `DatoAcademico.ficha_raw`.
- [x] `manage.py check` sin errores; suite de pruebas en verde.

## Fuera de alcance (siguientes sprints / fase 2)
- Integración en línea con el SGA (fase 2): la interfaz `AcademicoProvider` ya
  está lista para sustituir la carga por archivo sin tocar el resto del sistema.
- Cálculo del puntaje/estrato socioeconómico con baremo (se hará junto a Becas/TS).
- Carga complementaria de docentes/administrativos (plantilla reducida).

## Cómo probar rápidamente
```bash
python manage.py migrate
python manage.py seed_inicial
# crear el período en el admin o por shell (código 2026-1), luego:
python manage.py cargar_ficha ruta/ficha.xlsx --periodo 2026-1 --dry-run
python manage.py cargar_ficha ruta/ficha.xlsx --periodo 2026-1
pytest apps/academico -q
```
