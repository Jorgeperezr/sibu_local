# Cómo se conectan entre sí las portables

La pregunta era: si cada profesional de la sección tiene SIBU portable en su
computador, ¿cuál es el medio para que estén conectados y qué aplicativo de
código abierto usar?

La respuesta corta: **NetBird** (BSD-3) para unir los computadores, y **una
sola instancia con los datos** a la que todas las portables llegan. Lo largo es
por qué, porque hay una decisión de arquitectura antes de elegir el programa.

## Primero: son dos problemas, no uno

Se confunden a menudo y llevan a sitios distintos:

1. **Unir los computadores** — que la portátil de Enfermería pueda hablar con
   la máquina donde están los datos, esté en la Unidad o en la casa de alguien,
   sin abrir nada a internet.
2. **Compartir los datos** — qué pasa cuando dos personas tocan la ficha de la
   misma persona.

El primero se resuelve con una red. El segundo **no**: se resuelve decidiendo
dónde viven los datos.

## La decisión que hay que tomar antes

### Lo que NO se debe hacer: repartir la base y sincronizarla

Es lo primero que se le ocurre a cualquiera —poner `datos\sibu.sqlite3` en
Syncthing, en Drive o en una carpeta compartida— y falla por tres sitios:

- **SQLite sobre red se corrompe.** No es una opinión: lo dice el propio
  proyecto SQLite. Dos escrituras simultáneas sobre un archivo en red dejan la
  base inservible, y con ella las historias clínicas.
- **Sincronizar archivos no resuelve conflictos, los multiplica.** Si dos
  personas atienden a la vez, Syncthing no sabe fusionar dos bases: guarda una
  y renombra la otra como «conflicted copy». Una de las dos consultas
  desaparece y nadie se entera.
- **Rompe el sello de Psicología.** La regla es absoluta: su contenido clínico
  no sale del servicio. Una copia de la base en el disco de cada profesional
  pone las sesiones de Psicología en el computador de Farmacia. El RBAC del
  sistema no lo impide, porque quien tiene el archivo lo abre con cualquier
  visor de SQLite y se salta la aplicación entera.

Ese tercer punto es el que decide. Los otros dos son técnicos y tendrían
remedio; este no.

### Lo que sí: una instancia con los datos, portables como clientes

```
   casa de Jorge            Unidad de Bienestar              casa de Andrea
  ┌───────────────┐        ┌──────────────────────┐        ┌───────────────┐
  │ SIBU portable │        │  SIBU servidor       │        │ SIBU portable │
  │  (el icono)   │◄──────►│  PostgreSQL          │◄──────►│  (el icono)   │
  │               │        │  una sola base       │        │               │
  └───────────────┘        └──────────────────────┘        └───────────────┘
          └──────────── red privada (NetBird) ────────────────────┘
```

- **Los datos están en un sitio y solo en uno.** El RBAC vuelve a ser efectivo:
  nadie tiene el archivo, así que nadie se lo salta. El sello se sostiene.
- **No hay conflictos que resolver.** Una base, una verdad.
- **Las protecciones de concurrencia vuelven a funcionar.** En PostgreSQL
  `select_for_update()` bloquea de verdad; en SQLite es un no-op (ver
  `docs/PORTABLE.md`).
- **La portable sigue siendo portable**: la misma carpeta, el mismo icono. Lo
  único que cambia es que en vez de levantar su propio servidor, abre el
  navegador contra el central. Está implementado:

  ```
  # en la carpeta, archivo portable\servidor.txt
  https://sibu.unl.edu.ec
  ```

  Con ese archivo, el icono abre el navegador en el servidor. Sin él, levanta
  el SIBU local. El mismo paquete sirve para los dos modos.

  La dirección se escribe como la escribiría cualquiera —`10.0.0.5:8000`,
  `sibu-unidad`— y el launcher le pone el esquema; y antes de abrir el
  navegador comprueba que el servidor contesta. Si no, **dice que puede ser la
  red privada sin conectar**, el servidor apagado o la dirección equivocada, y
  aclara que no se ha perdido nada: en este modo los datos no están en la
  carpeta. Un «no se puede conectar» del navegador no distingue entre esas
  tres cosas, y la primera es la más frecuente y la más fácil de arreglar.

El servidor puede ser la máquina de Oracle Cloud que ya está documentada en
`docs/ORACLE_CLOUD.md`, o un computador de la Unidad que quede encendido.

## El medio: una red privada entre los computadores

Hace falta porque el servidor **no debe estar abierto a internet** y los
profesionales no siempre están en la red de la UNL. Una red superpuesta (VPN de
malla) resuelve las dos cosas: cada computador recibe una dirección fija
privada, el tráfico va cifrado, y desde fuera no hay nada publicado.

### Comparación de las opciones de código abierto

| Aplicativo | Licencia | Para qué sirve aquí | Pega |
|---|---|---|---|
| **NetBird** | BSD-3 | WireGuard con consola web y servidor de coordinación **autohospedable**. Se instala el cliente, se entra con la cuenta y el computador queda en la red. | Hay que levantar el coordinador (o usar su nube gratuita hasta 100 equipos). |
| **Headscale** | BSD-3 | Servidor de coordinación libre para los clientes de Tailscale (también BSD-3). Muy maduro y muy documentado. | El cliente lo publica una empresa; el servidor libre lo mantiene la comunidad. |
| **Nebula** (Slack) | MIT | Malla con certificados propios. Ligerísima, sin consola: se administra con archivos. | Sin interfaz: alguien tiene que llevar los certificados a mano. |
| **WireGuard** | GPLv2 | El cifrado que usan casi todos los de arriba por dentro. Con 5–10 equipos fijos es perfectamente llevadero. | Claves y direcciones a mano, equipo por equipo. |
| **OpenVPN** | GPLv2 | El clásico. Vale si la UNL ya tiene un servidor montado y se quiere aprovechar. | Más lento y más configuración que WireGuard. |
| ~~ZeroTier~~ | BSL 1.1 | — | **Ya no es software libre** desde 2019. Por eso queda fuera. |

### Recomendación

**NetBird**, por tres razones concretas para esta Unidad:

1. **Se administra desde una pantalla.** Dar de alta o de baja un computador no
   exige editar archivos ni reiniciar nada. En una unidad universitaria, donde
   quien administra no es necesariamente de sistemas, eso decide.
2. **El coordinador se puede autohospedar**, en la misma máquina de Oracle. No
   hay dependencia de un servicio ajeno para que la Unidad siga funcionando.
3. **BSD-3 de punta a punta**, cliente y servidor. Sin sorpresas de licencia
   como la de ZeroTier.

Si no hay quien administre nada y los computadores son siempre los mismos,
**WireGuard a secas** es menos trabajo total: se configura una vez y se olvida.

## Para los archivos: Syncthing, pero no para la base

Lo que sí se puede sincronizar entre computadores sin peligro:

- **Respaldos** de la base (`pg_dump` comprimido) hacia un segundo equipo.
- **Documentos y evidencias** que no sean la base.

Para eso, **Syncthing** (MPL-2.0): código abierto, sin servidor central, cifra
en tránsito y sincroniza carpeta a carpeta. Lo que **no** debe entrar nunca en
una carpeta de Syncthing es `datos\sibu.sqlite3`, por lo dicho arriba.

## Si de verdad hace falta trabajar sin conexión

El caso real sería una brigada de salud en una parroquia sin cobertura. Si eso
va a pasar, hay dos caminos y conviene elegirlo a propósito:

1. **Registrar en papel y digitar después.** Suena pobre y es lo que menos
   falla. Para una brigada de un día, es la respuesta correcta.
2. **Replicación multi-maestro de verdad**, con **Apache CouchDB**
   (Apache-2.0), que está diseñado para eso: cada portable replica al volver a
   la red y los conflictos se resuelven con reglas explícitas. Es rehacer la
   capa de datos del sistema entero, y **hereda el problema del sello**: la
   réplica local vuelve a poner datos en el disco de cada quien, así que habría
   que replicar solo el servicio propio de cada profesional.

No recomiendo el segundo sin una necesidad demostrada. Es mucho sistema nuevo
para un problema que, de momento, nadie ha dicho que tenga.

## Resumen

| Qué | Con qué | Licencia |
|---|---|---|
| Unir los computadores | **NetBird** (o WireGuard a secas) | BSD-3 / GPLv2 |
| Dónde viven los datos | **Una instancia** con PostgreSQL | — |
| Qué es la portable | El **cliente**: el icono abre el navegador contra el servidor | — |
| Respaldos y evidencias | **Syncthing** | MPL-2.0 |
| La base de datos | **Nunca** por sincronización de archivos | — |
