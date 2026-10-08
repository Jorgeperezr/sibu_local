# Sprint 5 — Laboratorio Clínico

## Objetivo
Cerrar el ciclo de los exámenes: desde la orden que emite Medicina hasta la
entrega del informe al correo institucional del estudiante, con validación en
dos pasos y alerta inmediata de valores críticos.

## Alcance entregado

### Catálogo con valores de referencia
- **`ParametroExamen`**: cada examen agrupa parámetros con unidad, tipo de valor
  (numérico/cualitativo/texto) y **rangos de referencia diferenciados por sexo
  y edad** (informe 6.4), más umbrales de valor crítico.
- `aplica_a(sexo, edad)` elige el rango correcto para cada paciente.
- `ResultadoParametro` ahora enlaza al parámetro por FK (antes texto libre), lo
  que permite calcular el marcador automáticamente.

### Flujo de trabajo completo
```
creada → muestra_tomada → en_proceso → resultado → validado → publicado
              ↓
          rechazada (con motivo obligatorio)
```
- `tomar_muestra`: fase preanalítica con tipo de muestra y código de barras
  autogenerado (`M00000001`).
- `rechazar_muestra`: exige motivo (hemólisis, cantidad insuficiente…).
- `registrar_resultado`: calcula el marcador (normal/alto/bajo/crítico) contra
  el rango aplicable al paciente. Rechaza parámetros ajenos al examen.
- **`validar_orden`: segregación de funciones (informe 14.2) — quien registra
  los resultados NO puede validarlos.**
- `publicar_orden`: notifica al solicitante, alerta si hay críticos y envía el
  informe al correo institucional.

### Notificaciones y envío
- Notificación in-app al profesional solicitante al publicar.
- **Alerta destacada por valor crítico** con el detalle del parámetro.
- Envío del informe al correo institucional del paciente, con aviso explícito
  de que **el informe no constituye un diagnóstico**.
- Si la persona no tiene correo institucional, **no falla en silencio**: deja
  constancia in-app para entrega en ventanilla.

### API REST
- `GET /api/v1/laboratorio/examenes/` — catálogo con parámetros y referencias.
- `GET /api/v1/laboratorio/ordenes/pendientes/` — cola, urgentes primero.
- `POST .../{id}/tomar-muestra/`, `.../rechazar-muestra/`, `.../resultados/`,
  `.../completar/`, `.../validar/`, `.../publicar/`.

### Interfaz web
- `/laboratorio/` — bandeja con urgentes destacadas.
- `/laboratorio/<id>/` — ficha que muestra **solo las acciones válidas para el
  estado actual**; marcadores coloreados por severidad.

## Pruebas (13 nuevas, 63 en total)
Toma y rechazo de muestra, los cuatro marcadores, parámetro ajeno al examen,
segregación de funciones, envío de correo, constancia sin correo, alerta
crítica, publicación sin validar, registro sobre orden validada, rangos por
sexo, y priorización de urgentes.

## Criterios de aceptación (cumplidos)
- [x] Quien registra los resultados no puede validarlos.
- [x] Los marcadores se calculan contra el rango de sexo/edad del paciente.
- [x] Un valor crítico genera alerta inmediata al solicitante.
- [x] Al publicar, el informe llega al correo institucional del estudiante.
- [x] Sin correo institucional queda constancia para ventanilla.
- [x] No se publica sin validar; no se registra sobre orden validada.
- [x] `ruff check` y `ruff format --check` limpios; 63 pruebas en verde.

## Verificado end-to-end
Orden urgente → bandeja (destacada) → toma de muestra (`M00000001`) → resultado
crítico 6.2 g/dL → técnico intenta validar (**bloqueado 400**) → bioquímico
valida → publica → correo a `jorge.perez@unl.edu.ec` → alerta crítica al médico.

## Fuera de alcance
- PDF firmado del informe (módulo `firma`, S7). Hoy el correo va en texto plano.
- Interfaz de captura masiva por lote (S10, si el piloto lo demanda).

## Cómo probar
```bash
python manage.py migrate
# En /admin/: crear un Examen y sus ParametroExamen con rangos
python manage.py runserver 0.0.0.0:8000
# /laboratorio/ → abrir la orden creada desde /medicina/consulta/
pytest apps/laboratorio -q
```
En desarrollo los correos salen por consola (`EMAIL_BACKEND` de `dev.py`).
