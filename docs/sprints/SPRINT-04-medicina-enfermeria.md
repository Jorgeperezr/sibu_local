# Sprint 4 — Enfermería + Medicina (flujo clínico principal)

## Objetivo
Implementar el flujo clínico central: triaje de Enfermería reutilizable por
Medicina, historia clínica médica con diagnósticos CIE-10, y emisión de recetas
y órdenes de laboratorio desde la consulta.

## Alcance entregado

### Enfermería
- **`SignosVitales`** como modelo autónomo vinculado al **expediente** (no solo
  a una atención): esto permite el triaje rápido sin necesidad de crear una
  atención formal de enfermería, y que Medicina los herede (informe 6.2, 12.1).
- IMC calculado automáticamente (Decimal) a partir de peso y talla.
- **`AtencionEnfermeria`** con JSONB para procedimientos e inmunizaciones,
  más campos para charlas educativas grupales.
- `services.ultimo_triaje(expediente, horas_maximo=12)` — punto de reutilización.
- UI: `/enfermeria/triaje/<expediente_id>/` con tabla de tomas del día.

### Medicina
- **`AtencionMedicina`** (OneToOne con `Atencion`): anamnesis, revisión de
  sistemas y examen físico (JSONB), plan, días de reposo, próxima cita.
- **`Diagnostico`** CIE-10 con tipo (presuntivo/definitivo), condición
  (primera/subsecuente) y bandera `principal`; restricción única atención+CIE-10.
- Reglas de negocio:
  - Un solo diagnóstico principal por atención (al marcar uno nuevo, el
    anterior pierde la bandera).
  - No se modifica una atención firmada (inmutabilidad clínica, informe 4.2).
  - `cerrar_atencion` exige ≥1 diagnóstico y uno principal.
- API: `POST/GET/PATCH /api/v1/atenciones/medicina/` con acciones
  `diagnosticos`, `receta`, `ordenes-laboratorio`, `cerrar`.
  **El serializer expone `triaje`**: los signos vitales recientes se heredan
  automáticamente.
- **Filtrado RBAC en `get_queryset`**: el rol determina qué atenciones ve.
- UI: `/medicina/consulta/<pk>/` — escritorio clínico con triaje visible,
  gestión de diagnósticos y cierre; campos deshabilitados si está firmada.

### Farmacia (emisión) y Laboratorio (solicitud)
- `farmacia.emitir_receta`: numeración correlativa anual `RX-AAAA-NNNNNN`,
  vigencia configurable (`SIBU.RECETA_VALIDEZ_HORAS`, 72h por defecto).
- `farmacia.recetas_pendientes` y `caducar_recetas_vencidas` (cola para S6).
- `laboratorio.crear_orden`: aplica la regla del informe (5.2) de que **solo
  Medicina y Odontología** pueden solicitar exámenes.
- `laboratorio.ordenes_pendientes` (bandeja para S5).

## Pruebas (20 nuevas, 50 en total)
- Enfermería (5): IMC automático, signos del día, último triaje vigente/expirado.
- Medicina (5): creación de HC, único principal, sin duplicados, cierre con
  validaciones, inmutabilidad.
- Farmacia (6): numeración correlativa, vigencia, receta vacía, cantidad cero,
  atención firmada, caducidad.
- Laboratorio (4): creación desde Medicina, rechazo de servicio no autorizado,
  orden vacía, atención firmada.

## Criterios de aceptación (cumplidos)
- [x] El triaje de Enfermería se hereda automáticamente en la consulta médica.
- [x] Una atención no cierra sin diagnóstico principal.
- [x] Una atención firmada no admite modificaciones (dx, recetas, órdenes).
- [x] Psicología no puede solicitar exámenes de laboratorio.
- [x] Las recetas llevan numeración correlativa y vigencia de 72h.
- [x] `manage.py check` limpio; 50 pruebas en verde (S1+S2+S3+S4).

## Verificado end-to-end
Flujo completo probado con cliente web: triaje → iniciar consulta (triaje
visible) → diagnóstico CIE-10 → receta `RX-2026-000001` → orden de laboratorio
→ cierre de atención → API devuelve el triaje heredado.

## Fuera de alcance (siguientes sprints)
- S5: registro y validación de resultados de laboratorio + envío al correo
  institucional del estudiante.
- S6: despacho de farmacia con descuento de inventario (FEFO) y odontograma.
- Firma digital de la atención (módulo `firma`, S7).

## Cómo probar
```bash
python manage.py migrate
python manage.py seed_inicial
# Cargar catálogo CIE-10 y crear un medicamento/examen desde el admin
python manage.py runserver 0.0.0.0:8000
# /enfermeria/triaje/<expediente_id>/  → registrar signos
# /medicina/iniciar/<expediente_id>/   → abrir consulta
pytest apps/medicina apps/enfermeria apps/farmacia apps/laboratorio -q
```
