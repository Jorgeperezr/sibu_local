# Sprint 8 — Firma electrónica con FirmaEC

## Lo que dice la especificación oficial

Fuente: **Manual de Implementación Institucional FirmaEC Descentralizada 2.1.0**
(MINTEL, 11/10/2021), secciones 11 y 12. Aplicación de escritorio vigente:
**FirmaEC v4.0.0** (agosto 2025).

El mecanismo real no es *una* de las alternativas planteadas: son **tres piezas
que trabajan juntas**.

1. **Servicio REST** (`firmadigital-servicio`). SIBU hace
   `POST /servicio/documentos` con `X-API-KEY` y el PDF en Base64. Devuelve un
   **JWT** (HS256, payload `{cedula, sistema, ids, exp}`) que **caduca a los 5
   minutos**. El JWT no contiene el PDF.
2. **Protocolo `firmaec://`** — existe y es el mecanismo oficial. El instalador
   de FirmaEC registra un *Protocol Handler* en el sistema operativo. SIBU
   construye el enlace **en el servidor** y lo presenta como botón:
   ```
   firmaec://<sistema>/firmar?token=<JWT>&tipo_certificado=2&estampado=QR&razon=...&pre=true
   ```
   Al pulsarlo, el navegador entrega el enlace a la aplicación de escritorio.
3. **Callback REST del sistema requirente**. FirmaEC devuelve el PDF firmado
   invocando un endpoint **nuestro**, cuya acción el manual obliga a llamar
   `grabar_archivos_firmados`, y que debe responder el texto plano `OK`.

**No hay servicio en localhost ni API de escritorio.** La opción "servicio
local" que se planteaba no existe: la comunicación va navegador → SO → app, y el
retorno viaja servidor-a-servidor.

`tipo_certificado`: 1=Token USB, 2=Archivo `.p12`, 3=Tarjeta inteligente.

## Se cumplen los requisitos

| Requisito | Cómo |
|---|---|
| No implementar criptografía en Django | `apps/firma` no importa ninguna librería criptográfica; solo `hashlib` para huellas de integridad |
| No solicitar ni almacenar la contraseña | No existe ningún campo ni formulario que la pida. Hay una prueba que falla si alguien añade uno |
| La clave privada nunca al servidor | Solo viaja el PDF; el `.p12` lo abre FirmaEC en el equipo del usuario |
| Toda la operación criptográfica es local | La hace la app de escritorio |
| SIBU solo genera, invoca, recibe y almacena | Es literalmente lo que hace `services.py` |

## El punto de riesgo: el callback

`grabar_archivos_firmados` **no lo invoca el navegador del usuario**: lo invoca
el servidor de FirmaEC. No hay sesión ni CSRF. Lo único que lo protege es una
API Key — y escribe en el expediente de un paciente.

El propio manual lo advierte: *"Se debe realizar el control previo de los
documentos recibidos por el servicio web"*. Sin ese control, quien alcance el
endpoint adjunta el PDF que quiera a la historia clínica que quiera.

### El problema de correlación

El callback trae **solo `cedula` y `nombreDocumento`**. No hay ningún
identificador nuestro. El único anclaje posible es el nombre del archivo, así
que lleva embebido un token opaco de 32 bytes (`secrets.token_urlsafe`):

```
SIBU-<correlacion>.pdf
```

Ese nombre es, en la práctica, parte de la autenticación del callback. Por eso
es impredecible y no un id secuencial.

### Controles aplicados

1. **API Key en tiempo constante** (`hmac.compare_digest`). Sin clave
   configurada, se rechaza todo: un despliegue a medias no queda abierto.
2. **La cédula del firmante debe ser la de quien solicitó.** Sin esto,
   cualquier titular de un certificado válido firmaría el informe de otro.
3. **`firmasValidas` e `integridadDocumento` deben ser ambos true.**
4. **El archivo debe ser un PDF real** (cabecera `%PDF-`) y ≤ 15 MB.
5. **El certificado debe venir, ser válido y estar vigente.**
6. **Idempotencia**: un reenvío no sobrescribe una firma asentada;
   `select_for_update` cierra la carrera de dos callbacks simultáneos.
7. **El token expira**: a los 5 minutos la solicitud pasa a EXPIRADA.

## [BUG CORREGIDO] Los rechazos no dejaban rastro

`_registrar_rechazo` escribía el log de auditoría y después se lanzaba el
`ValidationError` que aborta la operación. Como todo estaba bajo el mismo
`@transaction.atomic`, **el rollback se llevaba también el registro del
rechazo**: los intentos fallidos no dejaban ninguna huella.

En una historia clínica eso está al revés: los intentos rechazados son los que
más interesa auditar. Ahora el registro vive en su propia transacción, fuera del
atomic del asentamiento. Cubierto por una prueba verificada por control.

## [DECISIÓN PENDIENTE DEL CLIENTE] Psicología y el firmador externo

Firmar implica que **el PDF sale de SIBU**: viaja al servicio FirmaEC y se
almacena temporalmente en su base de datos antes de volver firmado.

Eso choca de frente con la decisión ya tomada: *el contenido de Psicología es
inaccesible para cualquiera fuera del servicio, sin excepciones*. Un informe
psicológico enviado a un firmador externo sale del perímetro donde ese sello se
sostiene — y si el servicio es el **centralizado del MINTEL**, sale además de la
UNL.

**El RBAC no puede detener esto.** La fuga no ocurriría por un permiso mal
puesto sino por una tubería legítima. Por eso la puerta está en
`apps/firma/policy.py` y **cerrada por defecto**:

- `FIRMAEC_DESCENTRALIZADO_PROPIO = False` (por defecto) → Psicología no se
  puede firmar. El resto de servicios sí.
- `= True` → la institución **afirma** que su FirmaEC corre en su propia
  infraestructura. Solo entonces se habilita.

SIBU no puede verificar esa topología por sí mismo: es una declaración
institucional, consciente y auditable. No un valor por defecto.

## Arquitectura

```
apps/firma/
├── models.py     SolicitudFirma (preparada→enviada→firmada/fallida/expirada)
│                 FirmaDocumento (registro final, reutilizado del esqueleto)
├── client.py     único punto que habla con firmadigital-servicio
├── policy.py     qué contenido puede salir de la institución
├── services.py   orquestación + validación del callback
├── api.py        grabar_archivos_firmados + estado (polling)
├── views.py      panel de firma, descarga
└── urls.py
```

El callback cuelga de la raíz (`/grabar_archivos_firmados`) porque el manual
fija el nombre de la acción.

## Flujo de usuario

1. El profesional abre la atención y pulsa **Firmar electrónicamente**.
2. SIBU renderiza el informe a PDF con WeasyPrint y crea la solicitud.
3. SIBU pide el JWT a FirmaEC y muestra el botón **Abrir FirmaEC y firmar**.
4. El usuario pulsa → el SO abre FirmaEC → selecciona su `.p12` → ingresa su
   contraseña **allí**.
5. FirmaEC firma y devuelve el PDF a SIBU vía callback.
6. La pantalla se refresca sola y ofrece el documento firmado.

El paso 6 necesita **polling**: FirmaEC devuelve el PDF al *servidor*, no a la
pestaña. No hay ningún evento que el navegador pueda escuchar. La pantalla
pregunta cada 5 s durante ~5 min.

## Endpoints

| Ruta | Uso |
|---|---|
| `POST /grabar_archivos_firmados` | callback de FirmaEC (nombre obligatorio) |
| `/firma/solicitar/<atencion_id>/` | genera el PDF y abre el panel |
| `/firma/panel/<pk>/` | botón de firma y estado |
| `/firma/estado/<pk>/` | JSON para el polling |
| `/firma/descargar/<pk>/` | PDF firmado (auditado) |

## Configuración

```bash
FIRMAEC_SERVICIO_URL=https://impws.firmadigital.gob.ec/servicio  # preproducción
FIRMAEC_SISTEMA=sibu                # registrado ante FirmaEC
FIRMAEC_API_KEY=...                 # SIBU -> FirmaEC
FIRMAEC_CALLBACK_API_KEY=...        # FirmaEC -> SIBU (¡distinta!)
FIRMAEC_PREPRODUCCION=True
FIRMAEC_DESCENTRALIZADO_PROPIO=False
```

`FIRMAEC_SERVICIO_URL` debe ser **https** (se valida: `urlopen` acepta `file://`
y una URL mal configurada leería el disco del servidor).

## Pruebas (25 nuevas, 194 en total)

El foco está en el endpoint expuesto: sin API Key, con API Key incorrecta, sin
clave configurada, correlación inventada, cédula ajena, firma inválida,
integridad rota, certificado no vigente, archivo que no es PDF, reenvío
duplicado, solicitud expirada, y GET. Más el sello de Psicología en ambos
sentidos y la validación del esquema de la URL.

## Requisitos NO técnicos, previos a producción

FirmaEC no se "instala y ya". Antes de producción hace falta:

1. Aceptar los Términos y Condiciones del MINTEL.
2. Desplegar `firmadigital-api` y `firmadigital-servicio` (Java 11, WildFly,
   PostgreSQL) si se opta por descentralizado.
3. Delegar por oficio un **Administrador Institucional de FirmaEC (AIF)**,
   firmado por la máxima autoridad.
4. Publicar el callback en **puerto 443 con subdominio y SSL**.
5. Solicitar el registro al MINTEL adjuntando el informe de pruebas.

Sin el registro, FirmaEC advierte al usuario de un "potencial riesgo de
seguridad". **Esto es gestión institucional, no desarrollo.**

## Pendiente

- Becas fase 1 → siguiente sprint.
- Talleres y portal de autogestión.
