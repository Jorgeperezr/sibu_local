# Sprint 8d — Portal de autogestión

## El aislamiento es por identidad, no por rol

El portal es la primera superficie **pública** del sistema. Las bandejas de
profesionales aíslan por rol y servicio (RBAC); el portal aísla por identidad:
**toda consulta parte del expediente vinculado a la cuenta**, y ningún recurso
se busca por un id de URL sin filtrar por el expediente propio. Manipular el
`cita_id` del POST no alcanza la cita de otro, y el mensaje de error es el
mismo exista o no el recurso ajeno: no se enumera lo de otros.

## La vinculación: donde se concentran las defensas

Es el único punto de entrada, así que es donde un ataque intentaría entrar.

1. **El código de verificación viaja SOLO al correo institucional que consta en
   el dato académico.** Nunca a un correo digitado. Si el correo lo eligiera
   quien se registra, cualquiera vincularía el expediente de otra persona con
   su propia casilla. La posesión de la casilla institucional ES la prueba de
   identidad.
2. **El token se guarda hasheado** (SHA-256): un volcado de la base no permite
   completar vinculaciones ajenas. Caduca a las 48 h, un solo uso, comparación
   en tiempo constante.
3. **Sin correo institucional registrado → vinculación presencial.** El sistema
   no adivina identidades.
4. **El intento de vincular un expediente ya vinculado a otra cuenta se rechaza
   y queda auditado.** Puede ser un error; puede ser alguien probando.

### [MISMO BUG QUE EN FIRMA] El rechazo no dejaba rastro

El log del intento sospechoso vivía dentro del `@transaction.atomic` y el
`raise` lo revertía. **Es la segunda aparición del mismo patrón** (Sprint 8 lo
tuvo en el callback de firma). El atomic se acota a la escritura; el registro
del rechazo queda fuera. Detectado por su propia prueba y verificado por
control.

Lección para el equipo: *auditar y abortar no caben en la misma transacción*.

## Qué muestra el portal — y qué no

| Muestra | No muestra |
|---|---|
| Sus citas (agendar, cancelar) | Contenido clínico narrativo |
| Resultados de laboratorio **publicados** | Resultados en proceso o sin validar |
| Sus recetas y su estado | Notas, fichas, evoluciones |
| Sus becas y su estado | El proceso psicológico: ni motivo, ni riesgo, ni sesiones |
| Sus talleres | Nada de otros expedientes |

El estudiante **sí ve su cita con Psicología** —él la agendó, ya lo sabe— pero
nada del contenido del proceso. El acceso a la historia clínica completa tiene
su procedimiento formal; el portal no es ese canal. Hay una prueba que crea un
proceso psicológico con contenido sensible y verifica que ninguna pantalla del
portal lo filtra.

## Citas desde el portal

Reutiliza `turnos_disponibles` y `reservar_cita` del Sprint 3: la misma
validación de agenda, conflictos y bloqueos que ventanilla. Origen
`AUTOGESTION`, así los reportes distinguen el canal. **Límite de 3 citas
activas** por expediente: frena el acaparamiento de turnos sin castigar el uso
normal.

## Fronteras entre sesiones

- Un **usuario del portal no navega las vistas internas**: psicología, becas,
  talleres y derivaciones le devuelven 403 (probado). De paso se endureció la
  bandeja de talleres, que devolvía 200 vacío a un usuario sin servicios.
- Un **profesional no navega el portal** con su cuenta de trabajo. Si además es
  paciente, su acceso va por ventanilla: mezclar sesiones confundiría qué rol
  hizo qué en la auditoría.

## Pruebas (17 nuevas, 263 en total)

Vinculación (correo institucional forzoso, token hasheado/caducado/incorrecto,
expediente ya vinculado auditado, sin correo → presencial, profesional
rechazado), aislamiento (cancelación ajena, enumeración, panel solo propio,
psicología no filtrada, fronteras en ambos sentidos) y citas (agendar en turno
real, límite de activas, solo resultados publicados).

Una migración: `portal.0001_initial` (VinculacionPortal).
