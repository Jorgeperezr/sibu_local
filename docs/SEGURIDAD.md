# Control de acceso: cómo está montado y cómo no romperlo

Este documento describe lo que el código hace hoy, no lo que debería hacer. Si
algo aquí no coincide con `apps/usuarios/rbac.py`, manda el código y este
archivo está desactualizado.

## La regla que no se negocia

**El contenido clínico de Psicología no es accesible fuera del servicio.** Ni
para Dirección, ni para Coordinación, ni para administración, ni con acceso de
emergencia. `rbac.puede_ver_atencion` lo aplica sin excepciones:

```python
if servicio.codigo in SERVICIOS_CONFIDENCIALES:
    return user.rol_principal == Rol.PROFESIONAL and servicio.pk in servicios_del_usuario(user)
```

Tres consecuencias que cuestan caro olvidar:

1. **La existencia de un dato también identifica.** Que alguien tenga cita con
   Psicología dice que es paciente de Psicología. Por eso el calendario da
   conteos y no nombres, la trazabilidad oculta la fila entera —no solo el
   motivo— a quien no es de ninguno de los dos servicios implicados, y el
   tablero de Dirección suprime los conteos menores que `K_MINIMO`.
2. **El tratante entra antes que la regla.** `puede_ver_atencion` concede
   acceso a quien realizó la atención *antes* de mirar si el servicio es
   confidencial. Eso es correcto —un profesional ve lo suyo— y convierte
   «nombrarse tratante» en una vía de entrada: por eso
   `verificar_profesional_del_servicio` impide abrir una atención en un
   servicio ajeno.
3. **Una marca no es una protección.** La trazabilidad devolvía un campo
   `confidencial: True` y a continuación imprimía el motivo. Marcar sirve para
   pintar un candado; separar el dato de quien no debe verlo es otra cosa.

## Las cuatro capas

Ninguna basta sola. Un fallo en una no debería filtrar nada.

| Capa | Dónde | Qué hace |
|---|---|---|
| **Permiso de vista** | `permission_classes`, `_solo_personal()` | Rechaza antes de tocar datos. Es la única que protege el `create`: un POST no pasa por el queryset. |
| **Filtrado de queryset** | `get_queryset()` | Lo que no está en el queryset devuelve 404 aunque se adivine el id. Protege lista y detalle. |
| **Permiso de objeto** | `PuedeVerAtencion` | Aplica `puede_ver_atencion` a la fila concreta. Solo corre si la vista llama a `get_object()`. |
| **Regla de dominio** | `services.py` | Vive donde pasan la pantalla, la API y lo que se escriba mañana. |

**La capa de servicios es la que importa.** Las dos veces que un agujero
sobrevivió a una corrección fue porque la regla estaba en la vista y no en el
servicio: la pantalla de Psicología comprobaba el servicio con
`verificar_es_del_servicio` y el endpoint equivalente no comprobaba nada.

## Funciones y qué significa cada una

- **`puede_ver_expediente(user)`** — ¿es personal de la Unidad? Roles
  PROFESIONAL, COORDINADOR, DIRECTOR, ADMINISTRATIVO, LABORATORIO, FARMACIA, o
  administrador. Deja fuera a `USUARIO_FINAL`, que es la cuenta de un
  estudiante y trabaja por el portal.
- **`puede_ver_atencion(user, atencion)`** — la regla fina, con el sello.
- **`atenciones_visibles(user, queryset)`** — la anterior a nivel de consulta.
  **Devuelve cero para los roles FARMACIA y LABORATORIO**, por separación de
  funciones clínica. Usarla para filtrar recetas u órdenes deja al farmacéutico
  sin mostrador; para eso está la siguiente.
- **`visible_para_personal(user, queryset, campo_servicio=None)`** — el suelo
  común: hay que ser personal, y lo confidencial solo lo ve su servicio. No
  estrecha más. Un endpoint que necesite una regla más estrecha la aplica
  encima.
- **`verificar_profesional_del_servicio(perfil, servicio)`** — una atención se
  abre en el servicio propio.
- **`EsPersonalDeLaUnidad`** — el par de escritura de `visible_para_personal`.

## Al añadir un endpoint o una pantalla

**Endpoint (DRF):**

```python
class LoQueSeaViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        return visible_para_personal(
            self.request.user, super().get_queryset(), campo_servicio="atencion__servicio"
        )
```

`campo_servicio` solo si el modelo llega a un `Servicio`; si no, se omite.
Si el objeto cuelga de una `Atencion`, añada `PuedeVerAtencion` y llame a
`get_object()` dentro de cada `@action(detail=True)` —un action que consulta
por `pk` a mano se salta el permiso de objeto—.

**Pantalla web:** `@login_required` **no basta**. Solo pregunta si hay sesión,
nunca de quién. Añada la comprobación que corresponda:
`rbac.puede_ver_expediente`, `verificar_acceso_atencion` o
`verificar_es_del_servicio`.

## La bitácora

`LogAuditoria` registra quién hizo qué. Dos cosas que conviene saber antes de
tocarla:

- **Un rechazo no se puede escribir dentro de la vista.** `ATOMIC_REQUESTS`
  envuelve la petición y el `PermissionDenied` la aborta: el registro se iría
  con el rollback. Se apunta en el contexto y lo escribe `AuditoriaMiddleware`,
  que corre fuera del bloque atómico. Fuera de una petición no hay transacción
  que revierta nada, así que ahí se escribe en el acto.
- **La bitácora también está sellada.** Una línea que diga «X leyó la atención
  47 del expediente de María Pérez, servicio Psicología» filtra por detrás lo
  que el sello protege. La regla: el actor siempre se ve, el paciente no. El
  velo se decide por el campo `servicio`, así que **todo registro sobre una
  atención debe declararlo** —una prueba recorre el código y falla si alguno se
  lo deja—.

## Lo que sale de la Unidad en un documento

El informe estadístico de un servicio se puede acompañar de **anexos**: la
nómina de las personas atendidas y la evidencia de cada valor reportado —quiénes
componen el «14 mujeres»—. Un anexo nombra pacientes en un archivo que sale de
la Unidad, así que se rige por tres reglas:

- **Los servicios confidenciales no llevan anexo.** El informe agregado sí se
  genera —lo hace el propio servicio y son sus datos—, pero la lista de nombres
  cae bajo la misma regla que impide exportar su historial, y se comprueba con
  la misma función (`exportacion.verificar_exportable`) para que no haya dos
  criterios capaces de separarse.
- **La identidad va protegida salvo decisión expresa.** Cédula, teléfono, correo
  institucional y número de expediente no se imprimen a menos que quien genera
  el informe los marque y desactive la protección. El número de expediente está
  en esa lista porque se compone como `EXP-<cédula>`: publicarlo mientras se
  oculta la cédula sería publicar la cédula. En su lugar cada fila lleva un
  código correlativo del propio anexo (`A-001`), que permite citar una fila sin
  identificar a nadie fuera de él.
- **Lo que llevaba el documento queda en la bitácora.** El registro `EXPORT`
  guarda las variables, los anexos y si la identidad iba protegida: un informe
  con nómina identificada es una salida de datos personales y tiene que poder
  distinguirse después de una tabla de porcentajes.

Y una regla que no es de acceso sino de honestidad del dato: **el anexo no puede
contradecir al informe**. Las dos cosas se construyen sobre
`reportes.services.etiquetar`, no sobre dos consultas parecidas, y una prueba
comprueba que la suma de atenciones de cada bloque de evidencia es exactamente
la cifra reportada. Un anexo que no cuadra es peor que no tenerlo.

## Los dos barridos

No hay que acordarse de nada: dos pruebas recorren el sistema entero y una
puerta nueva entra sola.

- **`apps/core/tests/test_api_superficie.py`** recorre el router de la API. Un
  estudiante no puede leer filas (403 o lista vacía) ni escribir (403 o 405,
  **nunca 400** — un 400 es la validación diciendo que la autorización dejó
  pasar).
- **`apps/core/tests/test_web_superficie.py`** recorre el resolver de URLs. Lo
  que un estudiante SÍ puede abrir está en una lista con su razón: añadir algo
  ahí obliga a justificarlo a mano.

Ambos **siembran el sistema entero antes de mirar**. Sin datos todas las listas
salen vacías y la prueba pasaría afirmando nada, que es peor que no tenerla.

## Una trampa que no es de acceso pero cuesta igual

**Django no avisa de un atributo inexistente en una plantilla**: lo resuelve a
cadena vacía y sigue. `{{ receta.codigo }}` sobre un modelo cuyo campo se llama
`numero` no da error, da un hueco. La página responde 200, la prueba de estado
pasa y el paciente ve una fila en blanco.

Ninguna prueba que mire el contexto o el código de estado lo detecta. Lo que sí
lo detecta es comprobar que **lo propio aparece**, no solo que lo ajeno no
aparece: `assert receta.numero in contenido`.

## Lo que ya pasó

Por si sirve de aviso sobre por dónde vuelven estas cosas:

| Qué | Cómo |
|---|---|
| `resolver_por_cedula` | Tres puertas: la vista `buscar`, la API y el JSON del formulario de reserva. No solo revela: **crea** la persona y su expediente. |
| Listas sin filtrar | `ExpedienteViewSet.retrieve` comprobaba; `list` no. |
| Escrituras | Doce endpoints donde la autorización no llegaba a correr. Un estudiante se concedía una beca y creaba la agenda de un profesional. |
| Escalada por tratante | Un médico abría un proceso psicológico y quedaba de tratante. |
| Regla escrita sin implementar | `# placeholder: la validación de servicio-profesional es de RBAC`, seguido de `pass`. |
