# Sprint 9 — Tablero de gestión

## La regla: gestión, no contenido

El tablero existe para la Dirección y las Coordinaciones. Muestra demanda,
flujo e indicadores; **cero identidades**. Una prueba recorre el tablero
serializado completo y verifica que no contiene cédulas ni nombres.

### Supresión de celdas pequeñas

Psicología aparece como conteo agregado —la Dirección necesita conocer la
demanda del servicio— pero un desglose fino con **n pequeño identifica**: "2
pacientes de Psicología" en un cruce por carrera y periodo señala a la persona
casi tan bien como su nombre. Regla: en servicios confidenciales, los conteos
de pacientes distintos menores a 5 se reportan como `<5`. El total de
atenciones sí se muestra: es demanda, no identidad.

### El ausentismo se calcula sobre citas finalizadas

Ausencias ÷ (atendidas + no asistió), no sobre el total. Contra un total que
incluye reservas futuras y cancelaciones a tiempo, el indicador mentiría a la
baja.

## Indicadores

Atenciones y pacientes por servicio · citas (estados, canal, ausentismo) ·
derivaciones por destino y estado · **CPO-D promedio** (del JSON `indices`,
congelado al cerrar la atención) · **impacto psicopedagógico** (solo
seguimientos con ambos promedios) · laboratorio por estado · becas vigentes por
tipo · cobertura de talleres (personas, no asistencias). Todo reutiliza los
servicios de cada módulo: el tablero no reinventa cálculos.

## Acceso

`ADMIN_GENERAL`, `DIRECTOR`, `COORDINADOR`. Profesionales y usuarios del portal:
403 (probado). La exportación CSV queda **auditada** (quién exportó qué rango).

## Rutas

`/reportes/` (tablero con filtro de fechas) · `/reportes/exportar/` (CSV).

## Pruebas (11 nuevas, 274 en total)

Supresión en confidenciales y no en el resto, tablero sin identidades, acceso
por rol en ambos sentidos, exportación auditada, ausentismo bien calculado,
tablero vacío sin errores. Sin migraciones.
