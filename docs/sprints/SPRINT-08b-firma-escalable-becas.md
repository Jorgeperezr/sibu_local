# Sprint 8b — Firma intercambiable + Becas fase 1

## 1. La firma deja de ser un supuesto

FirmaEC era parte del sistema; pasa a ser **una implementación**. Se sigue el
mismo patrón que `AcademicoProvider` (Sprint 1): el resto de SIBU depende solo
de la abstracción `FirmadorProvider`.

Dos razones concretas, no arquitectura por gusto:

1. **FirmaEC no está disponible todavía.** Exige registro ante el MINTEL y un
   AIF delegado por oficio. Hasta entonces el sistema tiene que arrancar y
   funcionar con la firma apagada, **diciéndolo con claridad**, no reventando
   con un `ImproperlyConfigured` a mitad de una consulta clínica.

2. **El firmador puede cambiar.** El Acuerdo Ministerial 017-2020 permite usar
   otro sistema compatible con los certificados de ARCOTEL. Si la UNL cambia, el
   punto de cambio es `providers.py`.

| Proveedor | Efecto |
|---|---|
| `deshabilitada` (**por defecto**) | El sistema funciona. El PDF se genera y se descarga sin firmar. |
| `firmaec` | FirmaEC del MINTEL. |

**Apagar el firmador no apaga el informe.** Con la firma deshabilitada, el
documento se genera igual y hay una ruta para descargarlo sin firmar
(`/firma/descargar-original/<pk>/`, auditada).

La política de confidencialidad ahora pregunta **"¿este firmador saca el
documento de la institución?"** en vez de "¿es FirmaEC?". Un firmador interno no
plantea el problema del sello de Psicología, se llame como se llame. El
atributo es `FirmadorProvider.externo`.

El callback devuelve **404** si el firmador configurado no es FirmaEC: no se
acepta el retorno de un firmador que esta instalación no usa.

### Añadir un firmador nuevo

Heredar de `FirmadorProvider`, implementar cuatro métodos, registrarlo en
`_PROVEEDORES`. No se toca `services.py`, ni las vistas, ni las plantillas.

## 2. Becas — fase 1

**SIBU no adjudica ni desembolsa becas.** Eso lo hace el sistema institucional.
Aquí se registra quién es beneficiario, se verifica que siga matriculado y se
deja constancia del seguimiento. El ciclo convocatoria→adjudicación llega en
fase 2 vía `id_externo`.

Reutiliza `AcademicoProvider` para consultar la matrícula: si mañana se consulta
al SGA por API en vez de leer la réplica de la ficha, becas no cambia.

### [BUG DETECTADO POR UNA PRUEBA]

`consultar_persona()` devuelve `None` **solo si la persona no existe**. Si
existe pero no tiene datos académicos cargados, devuelve un dict con `estado`
vacío. El código lo interpretaba como *"no matriculado"*.

Consecuencia real: se habría marcado sin matrícula a un becario **porque nadie
subió el archivo del periodo** — y de ahí a suspenderle la beca hay un paso.

Ausencia de dato no es prueba de ausencia de matrícula. Ahora el vacío significa
"no se sabe" (`matricula_vigente = None`), y la pantalla lo dice. Cubierto por
una prueba verificada por control.

### Reglas que protegen a la persona becada

- **`verificar_matricula` NO suspende.** Una beca es el sustento de alguien;
  quitarla es una decisión de Trabajo Social, no el efecto secundario de una
  consulta automática. El sistema informa; la persona decide.
- **Suspender o terminar exige causal escrita.** Sin ella, un reclamo posterior
  es indefendible — y el reclamo llega.
- **Una beca terminada no revive.**
- **No se duplica una beca activa del mismo tipo.** El duplicado se leería como
  dos adjudicaciones y falsearía cualquier conteo.
- **`expirar_vencidas` cierra por plazo, no por sanción.** No exige causal, pero
  deja escrito el motivo.

### [DECISIÓN PENDIENTE] Datos bancarios

`BecaBeneficiario.datos_bancarios_cifrados` **queda bloqueado**. `services.
guardar_datos_bancarios()` lanza ValidationError a propósito.

Dos razones:

1. **SIBU no desembolsa.** Custodiar cuentas bancarias sería asumir la
   responsabilidad de protegerlas sin obtener nada a cambio.
2. **El nombre del campo exige un cifrado que el proyecto no tiene.** No hay
   dependencia de `cryptography` ni gestión de claves. Escribir texto plano en
   un campo llamado *"cifrados"* es **peor que no tener el campo**: cualquiera
   que lea el esquema asumirá una protección inexistente.

Habilitarlo requiere una decisión del cliente y un sprint propio: dependencia de
cifrado, custodia y rotación de la clave, y una razón para que el dato viva
aquí. El serializer tampoco lo expone.

## API

| Ruta | Uso |
|---|---|
| `GET/POST /api/v1/becas/beneficiarios/` | listar / registrar |
| `POST .../{id}/seguimientos/` | entrevista, novedad, informe social |
| `POST .../{id}/verificar-matricula/` | consulta el dato institucional |
| `POST .../{id}/estado/` | suspender / terminar (causal obligatoria) |
| `GET .../vigentes/?periodo=N` | vigentes + resumen por tipo |
| `GET /api/v1/becas/tipos/` | catálogo |

## Interfaz web

| Ruta | Pantalla |
|---|---|
| `/becas/` | bandeja del periodo vigente + conteo por tipo |
| `/becas/ficha/<pk>/` | verificación, seguimientos, estado |

La pantalla dice explícitamente que verificar la matrícula **no suspende la
beca**, y que la causal es obligatoria.

## Pruebas (27 nuevas, 221 en total)

- **Firma (6 nuevas, 31 en total)**: defecto sin firmador, FirmaEC sin
  configurar, firmador desconocido, iniciar sin firmador, callback con firmador
  ajeno, política con firmador interno.
- **Becas (21)**: registro, duplicados, auditoría, los cuatro casos de
  verificación de matrícula, causal obligatoria, beca terminada, datos
  bancarios bloqueados, vigentes, resumen y expiración.

Sin migraciones nuevas: el esquema de becas ya existía desde el Sprint 0.

## Pendiente

- Talleres (Google Drive) y portal de autogestión.
- Reportes y tableros (S9). `resumen_por_tipo` ya alimenta eso.
