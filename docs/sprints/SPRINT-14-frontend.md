# Sprint 14 — Capa visual temporal

## Qué es y qué no es

Una capa de estilo para que la interfaz **se vea y se navegue mejor**, sin
reescribir las 36 plantillas. **No** es la identidad visual definitiva: el logo
institucional, la paleta oficial de la UNL y la tipografía propia son un trabajo
de diseño posterior. Esto sube el piso; no pone el techo.

## La estrategia: dos archivos, no treinta y seis

`static/css/sibu.css` estaba **vacío** (27 bytes, solo un comentario): toda la
apariencia venía de Bootstrap por CDN. En vez de tocar cada plantilla, se
trabaja en dos sitios de los que todo lo demás hereda:

- **`sibu.css`** estiliza las clases de Bootstrap que las plantillas ya usan
  (`.card`, `.table`, `.badge`, `.navbar`, `.btn-primary`...). Un cambio aquí
  alcanza a las 36 páginas a la vez. Incluye: verde institucional (marcador de
  posición hasta tener el oficial), tarjetas con jerarquía y elevación al pasar
  el cursor, tablas legibles, acento bajo los títulos, señal de
  confidencialidad reutilizable, y foco visible para navegación por teclado.
- **`base.html`** gana lo que faltaba y estaba duplicado:
  - **Mensajes centralizados**: antes cada plantilla repetía su bloque de
    alerts; ahora `base.html` los pinta una vez (las que aún lo traigan siguen
    funcionando).
  - **Pie institucional** y layout a altura completa.
  - **Favicon en línea** (SVG como `data:` URI): elimina el `404 /favicon.ico`
    que ensuciaba cada carga, sin añadir un archivo.
  - Bloques `breadcrumb`, `extra_head` y `extra_js` para que las plantillas
    extiendan sin tocar la base.

## Producción

El favicon `data:` está cubierto por `CSP_IMG_SRC` (que ya incluye `data:`).
`collectstatic` recoge `sibu.css` con el resto del estático. Sin cambios de
configuración.

## Pruebas (5 nuevas, 314 en total)

No se prueban colores —eso es diseño—: se prueba que el cambio de la plantilla
base no rompa nada. Que la portada y el login rendericen con los estilos, que el
favicon inline esté presente, que un login fallido pinte su alert, y humo sobre
los módulos que heredan de base.html. Sin migraciones.

## Lo que queda para un sprint de diseño real

Color oficial de la UNL, logo, tipografía institucional, y una revisión módulo a
módulo de las plantillas densas (tablas anchas, formularios largos). Este sprint
deja la base lista para eso.
