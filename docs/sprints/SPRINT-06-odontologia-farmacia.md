# Sprint 6 — Odontología + Farmacia (despacho FEFO)

## Objetivo
Poner en operación el cuarto servicio clínico (Odontología) y cerrar el ciclo
del medicamento: hasta ahora Medicina recetaba, pero Farmacia no podía
entregar. Con este sprint la receta llega hasta las manos del estudiante y el
inventario queda trazado.

## Alcance entregado

### Odontología
- **Odontograma FDI tipificado**: `EstadoPieza` con 10 estados; `piezas_validas()`
  valida permanentes (11-48) y temporales (51-85). Una pieza "99" se rechaza
  antes de tocar la base.
- **Histórico conservado**: registrar un estado nuevo **no borra el anterior**;
  se agrega un registro de evolución. El estado vigente es el último.
- **Odontograma acumulativo por PACIENTE**, no por atención: la segunda visita
  ve lo levantado en la primera (`odontograma_vigente(expediente)`).
- **Índice CPO-D (OMS)**: cariados + perdidos + obturados, solo sobre dentición
  permanente, calculado sobre el estado **vigente**. Si una pieza cariada se
  obtura, deja de contar como cariada y pasa a obturada — el CPO-D no cambia
  (sigue siendo una pieza afectada), pero sus componentes sí.
- **Procedimientos que actualizan el odontograma**: si el catálogo define
  `estado_resultante`, una obturación en la pieza 16 deja el registro de
  evolución automáticamente. El catálogo es **editable por la Unidad** desde el
  admin, sin tocar código.

### Farmacia — FEFO
**FEFO (First Expired, First Out)**: se despacha primero lo que caduca antes.
No es FIFO: el orden de ingreso es irrelevante.

- `ingresar_lote`: rechaza stock ya caducado y un mismo número de lote con dos
  fechas de caducidad distintas.
- `despachar_item`: **reparte entre varios lotes** si el primero no alcanza;
  `select_for_update` evita sobreventa en concurrencia.
- `despachar_receta_completa`: entrega lo disponible y **reporta el faltante sin
  fallar** — así opera la farmacia real.
- Estado de la receta recalculado desde lo efectivamente despachado
  (emitida → parcial → despachada).
- `alertas_stock` (bajo mínimo) y `alertas_caducidad` (90 días).
- **Trazabilidad**: todo movimiento deja `MovimientoInventario`; el saldo del
  lote siempre puede reconstruirse desde la bitácora (informe 6.5).

### Interfaz web
- `/odontologia/consulta/<id>/` — odontograma visual de 32 piezas coloreadas
  por estado; clic abre modal. CPO-D en cabecera.
- `/farmacia/` — mostrador con cola de recetas y alertas de stock.
- `/farmacia/receta/<id>/` — despacho ítem por ítem; muestra los próximos lotes
  en orden FEFO **antes** de entregar, y los lotes consumidos después.
- `/farmacia/inventario/` — stock por medicamento y lotes por caducar.

### API REST
- `POST /api/v1/atenciones/odontologia/` + acciones `piezas`, `procedimientos`, `cerrar`
- `GET /api/v1/odontologia/catalogo/`
- `POST /api/v1/farmacia/lotes/ingresar/`, `GET .../lotes/{id}/movimientos/`
- `GET /api/v1/farmacia/recetas/pendientes/`
- `POST /api/v1/farmacia/recetas/{id}/despachar-item/` (detalla lotes consumidos)
- `POST .../despachar-todo/`, `POST .../anular/`
- `GET /api/v1/farmacia/alertas/`

## Pruebas (31 nuevas, 94 en total)
**Odontología (13)**: FDI válida/inválida, histórico conservado, CPO-D solo
permanentes, CPO-D usa estado vigente, procedimiento actualiza odontograma,
acumulativo entre atenciones, cierre exige odontograma, atención firmada.

**Farmacia (18)**: ingreso con movimiento, rechazo de caducado, mismo lote con
dos caducidades, reingreso suma, stock excluye caducados, **FEFO consume el que
caduca antes aunque ingrese después**, FEFO reparte entre lotes, no más de lo
prescrito, no sin stock, receta caducada, parcial→despachada, faltantes,
alertas, baja de caducados, anulación, saldo reconstruible.

## Verificado end-to-end
```
ODONTOLOGÍA
1. HC creada · 2. Odontograma web: 32 piezas dibujadas
3. Pieza 16 cariada → CPO-D 1, cariados 1
4. Pieza FDI 99 → rechazada
5. Obturación → CPO-D 1, cariados 0, obturados 1
6. Cerrar → índices congelados

FARMACIA FEFO
1. L-LEJANO(100u, cad 365d) PRIMERO; L-PRONTO(30u, cad 30d) DESPUÉS
2. Receta RX-2026-000001 (45 tabletas)
4. Despacho → L-PRONTO ×30, luego L-LEJANO ×15  ← FEFO, no FIFO
5. Receta despachada · 6. Stock 85 (100+30-45)
```

## Criterios de aceptación (cumplidos)
- [x] Piezas FDI inválidas rechazadas.
- [x] El odontograma nunca pierde histórico.
- [x] CPO-D calculado sobre estado vigente, solo permanentes.
- [x] Un procedimiento con estado_resultante actualiza el odontograma.
- [x] El despacho consume lotes por FEFO y reparte si hace falta.
- [x] No se despacha más de lo prescrito ni sin stock ni con receta caducada.
- [x] El saldo del lote es reconstruible desde los movimientos.
- [x] `ruff check` y `ruff format --check` limpios; 94 pruebas en verde.

## Fuera de alcance
- Receta impresa/PDF firmado (módulo `firma`, S7).
- Formulario web para emitir recetas desde Medicina: sigue siendo **solo API**.
- Ingreso de lotes por interfaz web: solo API y admin (S10 si el piloto lo pide).
- Índice de placa y periodontal: el modelo los admite en `indices`, pero solo
  se calcula CPO-D.
