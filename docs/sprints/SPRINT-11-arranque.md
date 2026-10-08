# Sprint 11 — Simplificar el arranque y el primer uso

Este sprint no añade funcionalidad: quita fricción. Sale de tres tropiezos
reales al levantar la web por primera vez.

## 1. `make up`: un comando en lugar de cinco pasos

Levantar SIBU en Codespaces exigía recordar dos `export` con interpolación de
variables de Codespaces, y **olvidar `CSRF_TRUSTED_ORIGINS` hacía que la página
cargara pero todos los formularios fallaran** con un error de CSRF que no
explica su causa. `scripts/dev.sh` (o `make up`) lo hace todo:

- Deriva `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` del entorno, o usa localhost
  fuera de Codespaces.
- Confirma la conexión a la base de datos antes de arrancar, con un mensaje
  claro si el contenedor `db` aún no responde.
- Aplica migraciones pendientes en vez de fallar más tarde.
- Si el puerto 8000 ya está ocupado —un servidor anterior sigue vivo—, lo dice
  y da el comando para liberarlo, en lugar del críptico
  «That port is already in use».

## 2. `make perfil`: el fin del bloque de shell frágil

Dar acceso al superusuario requería pegar un bloque de `shell` que **fallaba al
adivinar nombres de campo**: se intentaba `PerfilProfesional(cedula=...)`, pero
ese modelo no tiene `cedula` —la cédula vive en `Persona`, no en el perfil del
profesional—. Ahora es un comando de gestión:

```bash
python manage.py perfil_dev                 # sobre el único superusuario
python manage.py perfil_dev --usuario NAME  # si hay varios
```

Con los campos reales, verificado de punta a punta: crea el perfil, asigna los
9 servicios y pone el rol `admin_general`.

### La salvaguarda que importa

El perfil que crea **ve Psicología**: rompe el sello a propósito para poder
navegar. Por eso el comando **se niega a ejecutarse con `DEBUG=False`**. Que
exista la comodidad en desarrollo no puede convertirse en una puerta trasera en
el servidor real, donde cada profesional recibe solo su servicio por ventanilla
de administración. Hay una prueba que verifica esa negativa.

## 3. `Makefile` como puerta de entrada

`make help` lista todo. `make setup` deja la base lista la primera vez
(migraciones + datos + RBAC); `make up` levanta; `make perfil` da acceso;
`make worker` corre Celery. `make lint` ejecuta ruff check y ruff format por
separado —el `&&` ocultaba el fallo de formato, que ya nos costó un CI en rojo—.

## Por qué los comandos anteriores fallaban

No era la instalación: era la documentación. `sudo service postgresql start` y
`redis-server` daban «command not found» porque el entorno es **docker-compose**
—PostgreSQL y Redis corren en contenedores aparte (`db`, `redis`)—, así que sus
clientes no existen dentro del contenedor `web` y no hacen falta. La conexión
siempre estuvo disponible; sobraban los comandos, no faltaba un servicio.

## Pruebas (6 nuevas, 294 en total)

Asignación de los 9 servicios, negativa con `DEBUG=False`, resolución del
superusuario único, exigir elección si hay varios, error claro para usuario
inexistente e idempotencia. Sin migraciones.
