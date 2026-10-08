# Sprint 8c — Talleres y actividades grupales

## La regla que gobierna el módulo

**Un taller no es una atención clínica.** Es una actividad grupal. Casi todo lo
que el módulo hace —y sobre todo lo que *no* hace— sale de ahí.

### Registrar a alguien en un taller no le abre una historia clínica

Asistir a una charla de prevención no convierte a nadie en paciente. Abrir un
expediente clínico porque alguien entró a un taller sería registrar una
condición que no existe, y dejaría a esa persona dentro del sistema de salud
sin haberlo pedido.

- Si la persona **ya tiene** expediente → se vincula, para poder medir cobertura.
- Si **no** → se guarda la cédula y basta.

Hay una prueba que cuenta los expedientes antes y después y falla si el módulo
crea uno.

## Google Drive: una implementación, no un supuesto

Tercer uso del patrón, tras `AcademicoProvider` (S1) y `FirmadorProvider` (S8b).

El OAuth del Workspace institucional y el Shared Drive no existen todavía. El
módulo funciona igual: un taller se planifica, se ejecuta y se registran sus
participantes sin que Google exista.

| `TALLERES_ALMACEN` | Efecto |
|---|---|
| `local` (**por defecto**) | Almacén del propio servidor. Las evidencias de un taller no son datos clínicos. |
| `gdrive` | Google Drive institucional. |

El proveedor de Drive **falla honestamente** si se lo invoca sin el cliente de
Google integrado. Inventar un `file_id` habría dejado el módulo "funcionando"
mientras las evidencias se perdían.

## Reglas de negocio

- **`validado` significa "la institución lo conoce", no "asistió".** Un
  participante externo asistió igual: descontarlo falsearía la cobertura.
- **El snapshot congela el dato académico.** Si la persona cambia de carrera el
  año próximo, el taller siguió siendo para quien era ese día. Sin esto, los
  reportes históricos se reescriben solos.
- **Cédula validada con el módulo 10**, igual que el resto del sistema.
- **No se repite una persona ni cambiando la vía de registro**: por lista y
  luego por cédula es la misma persona dos veces.
- **Ejecutar exige participantes**; un taller sin nadie no se ejecutó.
- **Cerrar exige al menos una evidencia**; un taller sin respaldo no está
  documentado.
- **`cobertura()` cuenta personas, no asistencias.** Quien fue a tres talleres
  es *una* persona alcanzada. Confundirlos infla la cobertura, y ese número
  termina en un informe de gestión.
- Psicopedagogía y Trabajo Social siempre; **Salud solo si el Administrador lo
  habilita** (`TALLERES_SALUD_HABILITADO`).

## Seguridad

1. **El nombre del archivo lo propone quien sube.** Se elimina cualquier
   componente de ruta: `../../../etc/passwd` no escribe fuera de la carpeta del
   taller. Cubierto por una prueba.
2. **Sin fallback a `/tmp`.** Archivar evidencias institucionales ahí las
   perdería al reiniciar y las dejaría legibles para cualquier usuario del
   servidor. Si falta `MEDIA_ROOT`, el módulo lo dice.

## API

| Ruta | Uso |
|---|---|
| `GET/POST /api/v1/talleres/` | listar / crear |
| `POST .../{id}/participantes/` | registrar participante |
| `POST .../{id}/ejecutar/` · `.../cerrar/` | máquina de estados |
| `GET .../cobertura/?periodo=2026-1` | personas alcanzadas |

Cada servicio ve sus talleres: no es contenido clínico, pero sí trabajo de un
servicio.

## Interfaz web

| Ruta | Pantalla |
|---|---|
| `/talleres/` | bandeja + cobertura |
| `/talleres/<pk>/` | participantes, evidencias, estado |

La pantalla dice explícitamente que registrar a alguien **no le abre una
historia clínica**, y marca a los participantes externos como tales sin
descontarlos.

## Pruebas (25 nuevas, 246 en total)

Creación y habilitación por servicio, el expediente que no se crea, cédulas
inválidas, participante externo, duplicados por ambas vías, snapshot congelado,
máquina de estados completa, almacén intercambiable, escape de ruta y cobertura
que no infla.

Sin migraciones: el esquema ya existía desde el Sprint 0.

## Pendiente

- **Portal de autogestión** → sprint propio. Es una superficie pública con
  autenticación distinta, donde cada estudiante debe ver **solo lo suyo** y el
  sello de Psicología vuelve a estar en juego. Meterlo aquí habría repetido el
  error del Sprint 7: entregar dos cosas y hacer bien solo una.
- Reportes y tableros (S9). `cobertura()` ya alimenta eso.
