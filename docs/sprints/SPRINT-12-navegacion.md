# Sprint 12 — Navegación

## El problema

La portada daba la bienvenida pero no llevaba a ninguna parte: la única forma de
abrir un módulo era teclear su URL. Y adivinarla fallaba, porque 9 de los 15
módulos tienen página índice (`/citas/`, `/reportes/`...) mientras 6 solo se
abren desde un expediente concreto y piden un id (`/expediente/` daba 404). El
usuario quedaba en un callejón sin salida.

## La solución, derivada del RBAC

Un menú en la cabecera y accesos directos en la portada, **generados desde lo
que cada usuario puede ver** — no una lista fija. La fuente es
`servicios_del_usuario`, la misma que usan las vistas, así que el menú no puede
mostrar un enlace que la vista luego niegue con 403, ni ocultar uno permitido.

### Un único mapa de módulos

`apps/core/navegacion.py` tiene la lista `MODULOS`, y de ahí beben la cabecera y
la portada. Añadir un módulo es añadir una fila; aparece en los dos sitios a la
vez, sin listas paralelas que se desincronicen.

Cada módulo declara **cómo** se decide si se ve:
- `("servicio", "codigo")` — el usuario tiene ese servicio asignado.
- `("roles", {...})` — su `rol_principal` está en el conjunto (Reportes:
  solo Dirección y Coordinación).
- `("siempre", None)` — cualquier profesional autenticado (agenda,
  derivaciones, talleres, búsqueda de expedientes).

Un `USUARIO_FINAL` no navega los módulos internos: su menú es solo «Mi portal».
El admin ve todos los enlaces para poder recorrer el sistema; el acceso fino al
contenido lo sigue resolviendo cada vista.

Se expone con un **context processor** (`navegacion`), así el menú aparece en
todas las plantillas sin tocar cada vista.

## El 404 de `/expediente/`

`/expediente/` no tenía raíz — solo `/expediente/buscar/` y la ficha por id.
Ahora la raíz **redirige a la búsqueda**: la ruta obvia deja de morir en 404.

## Pruebas (10 nuevas, 304 en total)

El caso central —un profesional de Laboratorio ve «Laboratorio» y no
«Psicología»—, el psicólogo que sí ve Psicología, el admin que ve todo, Reportes
solo para Dirección, los módulos generales visibles para cualquiera, el usuario
del portal restringido a «Mi portal», el usuario sin perfil sin módulos de
servicio, el anónimo sin nada, la cabecera renderizada y el redirect de
expediente. Sin migraciones.
