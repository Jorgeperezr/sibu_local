# Sprint 7 — Psicología + Psicopedagogía + Trabajo Social + Derivaciones

## Objetivo
Completar los 9 servicios de la Unidad y conectarlos entre sí. Con este sprint
**todos los servicios quedan operativos** y el paciente puede circular entre
ellos con trazabilidad.

## Decisión funcional del cliente
> **El contenido de Psicología es inaccesible para cualquiera fuera del
> servicio. Ni la Dirección de Bienestar, bajo ninguna circunstancia,
> incluyendo break-the-glass.**

Esa decisión no se documenta y ya: se **prueba**. Y obligó a cerrar dos huecos
que no eran evidentes.

## Hallazgos y correcciones

### 1. Inconsistencia lista/detalle en el RBAC (corregida)
`atenciones_visibles()` listaba las atenciones de Psicología al equipo del
servicio, pero `puede_ver_atencion()` solo permitía abrir las del propio
tratante. **La lista mostraba lo que el detalle negaba.**

Ahora coinciden: el equipo del servicio accede (sin esto nadie podría cubrir a
un colega y el servicio no operaría) y nadie más, nunca. Hay una prueba de
consistencia que recorre todos los roles y verifica que nada listado sea luego
denegado.

### 2. El retorno de derivación burlaba el sello (cerrado)
`retorno_texto` vive en el modelo `Derivacion`, que **no pertenece al servicio
destino**. Si Medicina derivaba a Psicología y el psicólogo escribía su
evolución en el retorno, **el médico la leía** — el sello era burlable
escribiendo en el campo equivocado.

`retornar()` ahora descarta el texto clínico cuando el destino es confidencial
y lo sustituye por un acuse: quien derivó sabe que su paciente fue atendido y a
quién contactar, pero no qué se trabajó.

Igualmente, `referir_a_externo()` rechaza emisiones desde Psicología: el
resumen clínico saldría de la Unidad.

### 3. Tensión del protocolo de riesgo (resuelta)
El modelo original decía "riesgo alto dispara alerta al coordinador", pero el
coordinador no puede ver Psicología. Se resuelve notificando **sin contenido
clínico**: el coordinador sabe que existe un caso de riesgo y a quién contactar
para activar el acompañamiento institucional, sin leer la ficha.

### 4. Bug de zona horaria (corregido)
Detectado al simular el drop-in del sprint sobre un checkout limpio: el test de
contrarreferencia fallaba **según la hora del reloj**.

`creado_en` se guarda en UTC. En Loja (UTC-5) las 19:00 locales ya son las
00:00 UTC del día siguiente, así que comparar `creado_en.date()` (UTC) contra
`timezone.localdate()` (local) daba un día de diferencia. En producción habría
rechazado **toda contrarreferencia registrada entre las 19:00 y la medianoche,
todos los días**.

El mismo patrón estaba latente en `citas.reservar()`: la agenda se define en
hora local (el profesional atiende 08:00–16:00 en Loja, no en UTC), pero
`.weekday()`, `.date()` y `.time()` se aplicaban sobre el datetime tal cual
llegara. Una cita a las 20:00 en Loja es la 01:00 UTC del día *siguiente*: el
día de la semana también salía mal.

Ambos normalizan ahora con `timezone.localtime()`. Dos pruebas con `freezegun`
fijan la hora dentro y fuera de la ventana del bug; se verificó que fallan si
se revierte el fix.

## Alcance entregado

### Psicología
- Modelo alineado al esquema existente, sin renombrados destructivos.
- `EscalaPsicometrica`: catálogo con tramos editables por el área
  (`[{min, max, etiqueta, alerta}]`). PHQ-9, GAD-7, etc. sin tocar código.
- `aplicar_escala` valida el rango y **eleva el riesgo a ALTO automáticamente**
  si el tramo está marcado como alerta.
- Sesiones con numeración correlativa automática.
- No admite dos procesos activos en paralelo; el cierre exige ≥1 sesión.
- **El admin solo expone el catálogo de escalas**: las fichas no se administran
  desde ahí porque el admin de Django no aplica el RBAC de servicio.

### Trabajo Social
- `prepoblar_desde_matricula`: v1 con lo que el estudiante declaró (informe 7.3).
- `verificar_ficha` **nunca sobrescribe**: marca la anterior como no vigente y
  crea v(n+1). El puntaje decide becas, así que debe poder auditarse con qué
  datos se decidió en cada momento.
- `calcular_puntaje`: ingreso per cápita en SBU (parametrizable vía
  `ParametroSistema`, no hardcodeado) y estrato de vulnerabilidad.
- Visitas domiciliarias con georreferencia; rechaza fechas futuras.

### Psicopedagogía
- Pre-puebla el historial académico desde `DatoAcademico` ya cargado.
- `impacto()`: variación del promedio antes/después. **Solo cuenta seguimientos
  con ambos promedios**; los incompletos se reportan aparte para no falsear el
  indicador que alimentará los tableros (S9).

### Derivaciones
- Ciclo: enviada → aceptada → agendada → atendida → retornada, con rechazo
  justificado en cualquier punto previo.
- `atender()` valida que la atención sea del servicio **y** del paciente correcto.
- Impide derivar al mismo servicio y duplicar derivaciones abiertas.
- Bandeja con urgentes primero (Case/When explícito, no alfabético).
- `trazabilidad()` reconstruye el recorrido del paciente entre servicios.
- Referencia/contrarreferencia externa con validación de fechas.

## Pruebas (55 nuevas, 149 en total)
- **Sello de Psicología (7)**: director, coordinador, admin y médico no acceden
  ni con break-the-glass; el psicólogo sí; lista y detalle consistentes en todos
  los roles; el timeline oculta psicología a terceros.
- **Psicología (12)**, **Derivaciones (17)**, **Trabajo Social (11)**,
  **Psicopedagogía (8)**.

Prueba clave: el retorno de Psicología no filtra contenido clínico —
contrastada con Enfermería, que sí lo conserva.

## Criterios de aceptación (cumplidos)
- [x] Nadie fuera de Psicología ve su contenido, ni con break-the-glass.
- [x] El retorno de derivación no transporta contenido confidencial.
- [x] El riesgo alto notifica sin filtrar contenido clínico.
- [x] La ficha socioeconómica conserva todas sus versiones.
- [x] El impacto académico no se falsea con datos incompletos.
- [x] `ruff check` y `ruff format --check` limpios; 149 pruebas en verde.

## Fuera de alcance
- **API y UI de estos 4 módulos**: este sprint entrega modelos, lógica y
  pruebas. Las interfaces van en un sprint de cierre (ver más abajo).
- Firma digital de informes (módulo `firma`).
- Consentimiento informado digital para Psicología.

## Nota importante sobre el alcance
El sprint prioriza **el núcleo de negocio y su corrección** por encima de la
superficie. Los 4 módulos tienen lógica y pruebas completas, pero **aún no
tienen API ni interfaz web**: no son usables por un profesional todavía. Se
requiere un sprint adicional (7b) para exponerlos.
