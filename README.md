# SIBU portable

Sistema Integral de Bienestar Universitario de la Universidad Nacional de Loja,
en versión **portable**: corre desde una carpeta, sin instalar nada. El
profesional pulsa un icono y se abre el navegador en la pantalla de
credenciales.

    python portable/crear_cuenta.py   # la primera vez
    python portable/arrancar.py       # y ya

En Windows, `portable\preparar_windows.ps1` arma la carpeta completa —con su
propio Python dentro— y después basta el acceso directo a `portable\SIBU.bat`
con el icono `portable\sibu.ico`.

- **Cómo armarla y qué saber antes de usarla en serio:** `docs/PORTABLE.md`
- **Cómo se conectan entre sí los profesionales:**
  `docs/CONEXION_ENTRE_PORTABLES.md`

El repositorio original —`Jorgeperezr/sibu`— queda archivado; aquí continúa el
desarrollo.

---

Plataforma web institucional para la administración unificada de los servicios
de la Unidad de Bienestar Universitario de la **Universidad Nacional de Loja**:
Medicina, Enfermería, Odontología, Laboratorio Clínico, Farmacia, Psicología,
Psicopedagogía, Trabajo Social y Becas.

> Documento base funcional y técnico: `docs/Informe_Tecnico_SIBU_UNL.md`.

## Stack

- **Backend:** Python 3.12 · Django 5 · Django REST Framework
- **Base de datos:** PostgreSQL 16
- **Frontend:** HTML5 · CSS3 · JavaScript · Bootstrap 5
- **Asíncrono:** Celery + Redis
- **Entorno de desarrollo:** GitHub Codespaces → macOS Intel (dev container)

## Arranque en Codespaces: un solo comando

> **Antes de nada, compruebe la rama.** El trabajo vive en
> `claude/sibu-onboarding-setup-pp2hws` hasta que se fusione el PR. Un
> `git pull` estando en `main` responde «Already up to date» y no trae nada:
>
> ```bash
> git branch --show-current          # ¿en qué rama está?
> git checkout claude/sibu-onboarding-setup-pp2hws
> ```

Abrir el repositorio en un Codespace y, cuando la terminal esté lista, escribir:

```bash
make up
```

Eso es todo. No hace falta `cp .env.example .env`, ni `createsuperuser`, ni
`runserver`, ni exportar variables.

`make up` hace por su cuenta lo que antes había que recordar: deriva el dominio
que Codespaces asigna al puerto 8000 (sin eso, todos los formularios fallan con
un error de CSRF), comprueba que PostgreSQL responda y deja la base al día. La
primera vez tarda un minuto; las siguientes, un segundo.

**Después de un `git pull` no hay que hacer nada más.** `make up` compara lo que
hay en la base con lo que el código define y decide solo: aplica las migraciones
que falten y vuelve a sembrar si la actualización trajo cuentas, servicios o
permisos nuevos. Antes eso obligaba a acordarse de `make demo` a mano, y no
acordarse se parecía mucho a «las credenciales no funcionan».

Al terminar imprime la URL. Púlsela, o abra el puerto 8000 en la pestaña
**PORTS** de VS Code.

### Con qué usuario entrar

`make up` imprime las credenciales la primera vez. Para volver a verlas:

```bash
make cuentas
```

| Usuario | Ve |
|---|---|
| `1104346091` / `1104346091` | Los nueve servicios, la carga de la base institucional y `/admin/` |
| `jhoely.lalangui`, `jorge.perez`, `daniel.cabrera`, … (contraseña = usuario) | Solo su servicio |
| `laboratorista`, `farmaceutico`, `trabajadora`, `becas` / `sibu-demo-2026` | Solo su servicio |
| `administrador` / `sibu-demo-2026` | Base institucional y gestión, sin contenido clínico |
| `director` / `sibu-demo-2026` | Tablero de gestión, sin contenido clínico |
| `estudiante` / `sibu-demo-2026` | Portal del paciente (`/portal/`) |

Cada profesional ve **solo su servicio**: no es una limitación del entorno de
prueba, es el comportamiento real del sistema.

### Si algo falla

| Lo que ve | Qué pasa |
|---|---|
| El navegador dice *Not Found* o pide iniciar sesión en GitHub | El puerto está privado. Pestaña **PORTS** → clic derecho en el 8000 → *Port Visibility* → **Public**. |
| *That port is already in use* | Quedó vivo un servidor anterior: `kill $(lsof -ti:8000)` y repita `make up`. |
| La página sale sin estilos: la barra lateral desmontada y los enlaces en fila | El navegador se quedó con una copia vieja o a medias del CSS. Recargue forzando: **Ctrl+Shift+R** (Cmd+Shift+R en Mac). Los enlaces a estáticos llevan la versión del archivo desde entonces, así que no debería repetirse. |
| El usuario y la contraseña no son aceptados | Compruebe cuáles existen con `make cuentas`. Desde un `git pull`, `make up` repone solo las cuentas que el código define; si aun así falta la suya, fuércelo con `make preparar`. |
| *La verificación CSRF ha fallado* al iniciar sesión | La propia pantalla lo explica ahora: dice qué Origin llegó, cuáles acepta el servidor y qué hacer. Lo más común: arrancó con `make run` en vez de `make up`, o está en una rama que no trae el arreglo (`git branch --show-current`). |
| *sin conexión a la base de datos* | El contenedor `db` aún no levantó. Espere unos segundos y repita, o *Rebuild Container*. |

> **`.env` no se usa en desarrollo.** `.env.example` es una plantilla de
> **producción**: trae `SECRET_KEY` vacía y `DEBUG=False`. Copiarla a `.env`
> para trabajar en Codespaces no hace falta y solo estorba.

## Comandos útiles (Makefile)

| Comando        | Acción                                            |
|----------------|---------------------------------------------------|
| `make up`      | **Arranque.** Prepara la base si hace falta y sirve |
| `make cuentas` | Recordar con qué usuario iniciar sesión           |
| `make preparar`| Rehacer estructura, permisos, CIE-10 y cuentas    |
| `make perfil`  | Dar a una cuenta acceso a todos los servicios     |
| `make test`    | Pruebas con cobertura                             |
| `make lint`    | Ruff + Bandit                                     |
| `make worker`  | Celery worker + beat                              |

## Despliegue en un servidor real

Ahí sí hace falta `.env`, y ahí `SECRET_KEY` vacía debe seguir abortando el
arranque: una clave adivinable firma sesiones reales. El procedimiento completo
está en `docs/DESPLIEGUE.md`; en resumen:

```bash
cp .env.example .env      # y completarlo: SECRET_KEY, ALLOWED_HOSTS, DATABASE_URL...
python -c "import secrets; print(secrets.token_urlsafe(64))"   # para SECRET_KEY
python manage.py check --deploy
python manage.py preparar --sin-demo   # sin cuentas ni pacientes ficticios
python manage.py createsuperuser
```

## Estructura

```
config/            Configuración (settings por ambiente, urls, celery)
apps/              Apps de dominio (core, usuarios, academico, expediente,
                   servicios clínicos, becas, talleres, transversales)
api/v1/            Capa REST (routers, endpoints)
templates/ static/ Frontend (Bootstrap 5)
docs/              Informe técnico y documentación
.devcontainer/     Entorno reproducible (Codespaces / macOS)
```

## Seguridad

Sistema con datos de salud y académicos sensibles: MFA, RBAC por servicio,
cifrado de campos, auditoría inmutable y buenas prácticas OWASP. No cargar
datos reales en entornos de desarrollo.

## Hoja de ruta (fases)

- **Fase 1:** base institucional por carga Excel/CSV, servicios clínicos,
  becas (beneficiarios + seguimiento), talleres con evidencias en Google Drive.
- **Fase 2:** integración API con el SGA y con el sistema de becas institucional.

## Documentación

| | |
|---|---|
| [`docs/OPERACION.md`](docs/OPERACION.md) | Qué se ejecuta cada día y qué significa lo que responde. |
| [`docs/SEGURIDAD.md`](docs/SEGURIDAD.md) | El control de acceso tal como está montado, y qué hacer al añadir un endpoint o una pantalla. |
| [`docs/COMO_CARGAR_LA_BASE.md`](docs/COMO_CARGAR_LA_BASE.md) | La carga de la base institucional, paso a paso. |
| [`docs/CARGA_BASE_INSTITUCIONAL.md`](docs/CARGA_BASE_INSTITUCIONAL.md) | El diccionario de las 157 columnas. |
| [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md) | Lo que el código no puede verificar por sí mismo. |
| [`docs/Informe_Tecnico_SIBU_UNL.md`](docs/Informe_Tecnico_SIBU_UNL.md) | El informe técnico: alcance, modelo de datos, requerimientos, flujos. |
