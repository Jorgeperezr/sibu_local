# Sprint 7b — API REST e interfaz web de los 4 módulos

El Sprint 7 entregó modelos, lógica y pruebas de Psicología, Psicopedagogía,
Trabajo Social y Derivaciones, pero sin API ni UI: los módulos eran correctos y
a la vez inusables. Este sprint los expone.

Alcance acordado: **solo API + UI**. La firma digital de informes se traslada al
Sprint 8, junto a Becas.

## La API es una superficie nueva para el sello

El RBAC puede estar perfecto y un viewset mal configurado filtrar Psicología
igual. El control no puede depender de una sola capa, así que se protege por
partida doble:

1. `get_queryset` filtra con `rbac.atenciones_visibles`. Para quien no es del
   servicio la lista sale **vacía**, no "prohibida": no se revela ni la
   existencia del proceso.
2. `PuedeVerAtencion` (nuevo permiso DRF reutilizable) aplica
   `rbac.puede_ver_atencion` al objeto. El detalle se cierra aunque alguien
   adivine el id.

Un fallo en cualquiera de las dos capas no basta para filtrar contenido.

### El serializer de Derivaciones

`atencion_destino` se expone **solo como id y nombre de servicio, nunca
anidado**. Anidarlo habría serializado el contenido clínico de la atención de
Psicología y se lo habría entregado al médico que derivó — exactamente lo que
el sello impide, por una puerta que el RBAC no vigila. El `retorno_texto` ya
viene saneado desde `services.retornar()`.

## [HUECO CORREGIDO] RBAC ausente en las vistas web del Sprint 6

Al construir esta UI se detectó que `odontologia.views.consulta()` exigía solo
`@login_required`. **Cualquier usuario autenticado abría la historia clínica de
cualquier paciente cambiando el id en la URL.**

Las vistas de plantilla no pasan por los permisos de DRF: necesitan su propia
comprobación. Se agrega `apps/usuarios/decorators.py` con
`verificar_acceso_atencion`, se aplica a Odontología y se cubre con una prueba
de regresión verificada por control (falla si se revierte el fix).

No es el sello de Psicología —es un salto horizontal entre pacientes— pero era
real y estaba en producción desde el Sprint 6.

## API

| Método | Ruta | Efecto |
|---|---|---|
| GET | `/api/v1/psicologia/escalas/` | catálogo (sin datos de pacientes) |
| POST/GET | `/api/v1/psicologia/fichas/` | abrir / listar procesos |
| POST | `/api/v1/psicologia/fichas/{id}/sesiones/` | registrar sesión |
| POST | `/api/v1/psicologia/fichas/{id}/escalas/` | aplicar escala |
| POST | `/api/v1/psicologia/fichas/{id}/riesgo/` | marcar riesgo |
| POST | `/api/v1/psicologia/fichas/{id}/cerrar/` | cerrar proceso |
| GET | `/api/v1/trabajo-social/fichas/?expediente=N` | historial de versiones |
| POST | `/api/v1/trabajo-social/fichas/prepoblar/` | crear v1 desde matrícula |
| POST | `/api/v1/trabajo-social/fichas/verificar/` | crear v(n+1) verificada |
| POST/GET | `/api/v1/psicopedagogia/fichas/` | fichas |
| POST | `/api/v1/psicopedagogia/fichas/{id}/seguimientos/` | registrar seguimiento |
| GET | `/api/v1/psicopedagogia/fichas/{id}/impacto/` | variación del promedio |
| GET/POST | `/api/v1/derivaciones/` | listar / derivar |
| GET | `/api/v1/derivaciones/bandeja/?servicio=N` | bandeja de entrada |
| POST | `/api/v1/derivaciones/{id}/{aceptar,rechazar,agendar,atender,retornar}/` | ciclo |
| GET | `/api/v1/derivaciones/trazabilidad/?expediente=N` | recorrido |
| POST | `/api/v1/referencias-externas/` | referir a externo |
| POST | `/api/v1/referencias-externas/{id}/contrarreferencia/` | registrar retorno |

## Interfaz web

| Ruta | Pantalla |
|---|---|
| `/psicologia/` | bandeja de procesos activos, riesgo alto resaltado |
| `/psicologia/proceso/{id}/` | ficha, sesiones, escalas, riesgo, cierre |
| `/trabajo-social/ficha/{expediente}/` | ficha vigente + historial de versiones |
| `/psicopedagogia/` · `/psicopedagogia/ficha/{id}/` | bandeja, seguimientos, impacto |
| `/derivaciones/` | bandeja de entrada y salida |
| `/derivaciones/derivar/{atencion}/` | emitir derivación |
| `/derivaciones/trazabilidad/{expediente}/` | recorrido entre servicios |

Decisiones de pantalla que reflejan las reglas del negocio:

- Trabajo Social dice explícitamente que verificar **crea una versión nueva** y
  conserva la anterior; el historial está a la vista para que nadie crea que
  está sobrescribiendo.
- Psicopedagogía muestra cuántos seguimientos quedaron **fuera** del cálculo de
  impacto por no tener ambos promedios, en lugar de esconderlo en un promedio
  que parecería más sólido de lo que es.
- Al retornar desde un servicio confidencial, la pantalla avisa al psicólogo de
  que **solo viaja el acuse**, para que no escriba pensando que el otro lo leerá.

## Pruebas (20 nuevas, 169 en total)

- **API del sello (10)**: director, coordinador y admin no abren el detalle ni
  ven la lista (parametrizado por rol); un ajeno no puede escribir sesiones; el
  retorno de una derivación a Psicología no filtra la evolución.
- **UI del sello (8)**: el médico recibe 403 en el proceso y en la bandeja; los
  roles jerárquicos tampoco entran; no se registran sesiones ajenas.
- **Regresión de Odontología (2)**: verificada por control.

Se ordenan los querysets paginados: sin orden explícito la paginación puede
repetir u omitir registros entre páginas (`UnorderedObjectListWarning`).

## Verificado de extremo a extremo por interfaz web

Psicología (PHQ-9=22 eleva el riesgo a ALTO y lo muestra), sello (médico 403),
Trabajo Social (v1 pre-poblada → v2 verificada, 0.21 SBU, extrema
vulnerabilidad, historial conserva ambas), Psicopedagogía (impacto +2.50) y
Derivaciones (el médico deriva urgente, el psicólogo acepta/atiende/retorna, y
el retorno **no filtra** la evolución: el médico ve el acuse y la trazabilidad
marca el servicio como confidencial).

## Pendiente

- Firma digital de informes → Sprint 8.
- Becas fase 1 → Sprint 8.
