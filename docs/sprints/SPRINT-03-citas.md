# Sprint 3 — Módulo `citas` (agenda y ciclo de vida de la cita)

## Objetivo
Habilitar la agenda por profesional y el flujo completo de citas: reserva,
cambios de estado, reprogramación, cancelación y recordatorios. Es la
puerta de entrada operativa para todos los servicios clínicos.

## Alcance entregado
- **Modelos** (`apps/citas/models.py`):
  - `Agenda`: franjas recurrentes por profesional/servicio/día con vigencia
    y duración de turno configurable.
  - `BloqueoAgenda`: bloqueos puntuales (vacaciones, reuniones).
  - `Cita`: 8 estados canónicos del informe (Anexo A) con restricción única
    en BD que impide doble reserva activa al mismo profesional a la misma hora.
- **Lógica de negocio** (`apps/citas/services.py`):
  - `turnos_disponibles`: calcula huecos combinando agenda + bloqueos + citas.
  - `reservar_cita`: valida horario, conflicto y bloqueo (transaccional).
  - `cambiar_estado`: solo transiciones válidas; timestamps automáticos de
    llegada y atención.
  - `reprogramar`: crea cita nueva enlazada a la original (audit trail).
  - `cancelar`: solo desde estados permitidos.
- **API REST** (`/api/v1/`):
  - `citas/` (CRUD + acciones `reprogramar`, `cancelar`, `cambiar_estado`,
    `proximas`, `disponibilidad`).
  - `agendas/` y `bloqueos-agenda/`.
- **Interfaz web** (Bootstrap 5):
  - `/citas/` — agenda del día con cambio de estado inline.
  - `/citas/reservar/` — formulario con búsqueda por cédula, selectores
    encadenados servicio→profesional→fecha→turno vía fetch.
- **Recordatorios** (`apps/citas/tasks.py`):
  - `enviar_recordatorios(horas)` — Celery task idempotente que crea
    notificaciones sin duplicar. Programable en Beat cada 15 min para
    ventanas T-48h y T-24h.
- **Ajuste transversal**: `notificaciones.Notificacion` ahora acepta
  `usuario=null` con `destinatario_correo/destinatario_nombre` para dirigir
  avisos a pacientes sin cuenta interna (correo institucional).
- **Pruebas** (12): agenda, disponibilidad, reserva, conflictos, bloqueos,
  máquina de estados válida/inválida, reprogramación, cancelación,
  selectors y task de recordatorios.

## Criterios de aceptación (cumplidos)
- [x] No se pueden crear dos citas activas al mismo profesional a la misma hora (BD).
- [x] No se puede reservar fuera del horario de agenda ni sobre bloqueos.
- [x] La máquina de estados rechaza transiciones inválidas.
- [x] La reprogramación conserva la trazabilidad de la cita original.
- [x] El task de recordatorios no envía duplicados en ejecuciones repetidas.
- [x] `manage.py check` limpio; 29 pruebas en verde (S1+S2+S3).

## Cómo probar
```bash
python manage.py migrate
# Crear un profesional con agenda desde el admin, o por shell:
# from apps.citas.models import Agenda; Agenda.objects.create(...)
python manage.py runserver 0.0.0.0:8000
# Ir a /citas/ y /citas/reservar/
pytest apps/citas -q

# Task de recordatorios (con Celery corriendo):
# celery -A config beat -l info   # programar cada 15 min
# celery -A config worker -l info
```

## Siguiente sprint
S4 — `enfermeria` + `medicina` (triaje, HC médica, recetas y órdenes de laboratorio).
