# Sprint 13 — Pantalla de inicio de sesión

## El bug

`/cuentas/login/` devolvía **500**: `TemplateDoesNotExist: registration/login.html`.

`django.contrib.auth.urls` estaba enrutado desde el principio y `LOGIN_URL`
apuntaba a él, pero la plantilla nunca se creó. **El sistema no tenía pantalla
de acceso.** No se notaba porque se entraba por `/admin/`, que trae su propio
login; en cuanto una sesión caducaba o entraba alguien nuevo, la puerta de
entrada daba un error 500.

## La corrección

- `templates/registration/login.html`: formulario de acceso que extiende
  `base.html`, con mensaje de error claro y aviso cuando se llega por falta de
  permiso (`next`).
- `templates/registration/logged_out.html`: página de salida, como respaldo si
  algún día se quita `LOGOUT_REDIRECT_URL`.

Sin cambios de configuración: la infraestructura de auth ya estaba puesta
(`LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL`); solo faltaban las
plantillas que esperaba.

## Pruebas (5 nuevas, 309 en total)

Que la página cargue (antes 500), que un login correcto entre y redirija a la
portada, que uno incorrecto no autentique, que el logout cierre la sesión, y que
una vista protegida mande al login sin sesión. Sin migraciones.
