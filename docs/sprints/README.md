# Plan de Sprints — SIBU

Desarrollo incremental por sprints de 2 semanas, alineado al cronograma del
informe técnico (sección 17). Cada sprint entrega funcionalidad usable, probada
y desplegable.

| Sprint | Módulo / Objetivo | Estado |
|--------|-------------------|--------|
| **S1** | `academico` — carga de la ficha socioeconómica (Excel/CSV) | ✅ Entregado |
| S2 | `expediente` + `usuarios` — expediente único, RBAC, consulta por cédula en UI | ✅ Entregado |
| S3 | `citas` — agenda y ciclo de vida de la cita | ✅ Entregado |
| S4 | `enfermeria` + `medicina` — triaje, HC médica, recetas y órdenes | ✅ Entregado |
| S5 | `laboratorio` — órdenes, resultados y envío al correo institucional | ✅ Entregado |
| S6 | `odontologia` + `farmacia` — odontograma, despacho e inventario | ✅ Entregado |
| S7 | `psicologia` + `psicopedagogia` + `trabajo_social` + `derivaciones` | ✅ Entregado (lógica y pruebas) |
| S7b | API REST e interfaz web de los 4 módulos del S7 | ✅ Entregado |
| S8 | **firma electrónica con FirmaEC** | ✅ Entregado |
| S8b | firma intercambiable + `becas` (fase 1) | ✅ Entregado |
| S8c | `talleres` con almacén intercambiable | ✅ Entregado |
| S8d | portal de autogestión | ✅ Entregado |
| S9 | `reportes` + tableros + indicadores | Pendiente |
| S10 | Endurecimiento, pruebas de carga/penetración, piloto | Pendiente |

## Convención de ramas y commits

- Rama por sprint: `sprint/NN-modulo` → PR a `develop` → `main` al cerrar.
- Commits: `feat(academico): asistente de carga`, `test(...)`, `fix(...)`, `docs(...)`.
- Definición de "terminado": código + pruebas (cobertura del módulo ≥ 80 %) +
  `manage.py check` sin errores + documentación del sprint + CI en verde.
