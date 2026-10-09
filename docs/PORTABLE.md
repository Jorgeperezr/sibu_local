# SIBU portable

SIBU corriendo desde una carpeta, sin instalar nada. El profesional la copia a
su computador —o la lleva en una memoria—, pulsa el icono y se abre el
navegador en la pantalla de credenciales.

## Qué es «portable» aquí

La carpeta se lleva **todo** dentro: el código, su propio Python, la base de
datos, los adjuntos, el registro y la clave de la instalación. Copiarla a otro
computador se lleva la instalación entera. No hay servicio que registrar, ni
PostgreSQL que instalar, ni nada que quede en el perfil del usuario.

```
sibu_local\
├── portable\
│   ├── SIBU.bat            ← esto es lo que hay detrás del icono (Windows)
│   ├── sibu.sh             ← lo mismo en Linux y macOS
│   ├── sibu.ico            ← el icono
│   ├── arrancar.py         ← lo que hace el launcher
│   ├── crear_cuenta.py     ← la primera cuenta
│   └── preparar_windows.ps1 ← arma la carpeta, se ejecuta UNA vez
├── python\                 ← el Python que viaja con la carpeta
├── datos\                  ← la base, la clave, el registro, los adjuntos
│   ├── sibu.sqlite3
│   ├── clave.txt
│   ├── sibu.log
│   ├── correo\
│   └── media\
└── (el resto del sistema)
```

`datos\` **no está en el repositorio** y no debe estarlo: contiene datos de
pacientes y la clave de esa instalación.

## Armarla (una sola vez, en el computador que la prepara)

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File portable\preparar_windows.ps1
python\python.exe portable\crear_cuenta.py
```

Después, el icono: cree un acceso directo a `portable\SIBU.bat` en el
escritorio y en *Propiedades → Cambiar icono* elija `portable\sibu.ico`.

> **Aviso honesto.** `preparar_windows.ps1` no se ha podido ejecutar donde se
> escribió: el desarrollo corre en Linux. La lógica es la que documenta
> python.org para la distribución embebida —incluida la línea del archivo
> `._pth`, que es la causa número uno de que `import django` falle aunque
> Django esté instalado al lado—, pero la primera ejecución real en Windows
> hay que hacerla leyendo lo que imprime.

### Linux y macOS

```bash
pip install -r requirements/portable.txt
python portable/crear_cuenta.py
chmod +x portable/sibu.sh
./portable/sibu.sh
```

## Usarla

Pulsar el icono. Eso es todo. Por debajo:

1. Prepara la carpeta si hace falta (migraciones, servicios, roles, CIE-10).
   Es idempotente, así que corre en cada arranque y no cuesta nada cuando no
   hay nada que hacer.
2. Elige un puerto libre. No uno fijo: con uno fijo, abrir el programa dos
   veces da «address already in use» y quien lo ve no entiende por qué.
3. Levanta el servidor y abre el navegador **cuando ya responde**. Abrirlo
   antes enseña un «no se puede conectar» y quien lo ve cierra el programa
   pensando que no funciona.

Cerrar la ventana cierra el sistema.

## La primera cuenta

Sin ninguna cuenta el sistema levanta y rechaza a quien se escriba, que se
parece mucho a «las credenciales no funcionan». `crear_cuenta.py` lo resuelve, y
la **primera** nace como Administración General: desde *Perfiles* da de alta y
asigna servicios al resto.

Un detalle que costó encontrar y que conviene no repetir:
`Usuario.objects.exists()` **siempre** es cierto, porque la migración de
django-guardian deja su fila `AnonymousUser`. Preguntado así, la primera cuenta
nunca se reconocía como primera y nacía con «Consulta Restringida». La pregunta
correcta es `cuentas_de_persona().exists()`.

## Lo que hay que saber antes de usarla en serio

### La base es SQLite, y eso tiene consecuencias

En SQLite, `select_for_update()` **no bloquea**: el backend de Django declara
`has_select_for_update = False` y la llamada es un no-op. Las protecciones de
concurrencia que el sistema tiene en farmacia —el saldo de un lote, el doble
despacho— y en la ficha socioeconómica quedan sin efecto.

Con **un** profesional trabajando en **su** carpeta eso da igual: no hay dos
escrituras a la vez. Lo que no es una opción es compartir el mismo archivo
entre varios por una carpeta de red: SQLite sobre red se corrompe, y ahí sí
habría dos escrituras a la vez.

### La carpeta lleva datos de pacientes

Una memoria USB con `datos\sibu.sqlite3` es la historia clínica de la Unidad en
el bolsillo de alguien. Lo mínimo:

- **Cifre el disco** del computador (BitLocker en Windows, LUKS en Linux,
  FileVault en macOS). La carpeta no se cifra sola.
- En FAT32 —una memoria formateada de fábrica— **no hay permisos de archivo**,
  así que `clave.txt` queda legible para cualquiera que conecte la memoria.
  Use NTFS o exFAT con el disco cifrado, o mejor, no lleve la carpeta en una
  memoria.
- Si el computador se pierde, se pierde esa copia de los datos. No hay
  borrado remoto.

### El sello de Psicología sigue vigente

Las reglas del RBAC viajan con el código: una portable de un profesional de
Medicina no enseña contenido de Psicología aunque la base esté en su disco.
Pero **el archivo sí está en su disco**, y quien tenga el archivo y sepa abrir
un SQLite lee todo lo que haya dentro, saltándose la aplicación.

Esto no es un fallo que se pueda arreglar dentro de SIBU: es la consecuencia de
poner la base en el computador de cada quien. Por eso la arquitectura que se
recomienda en `docs/CONEXION_ENTRE_PORTABLES.md` **no** reparte la base: deja
una sola instancia con los datos y convierte la portable en el cliente que
llega a ella.

### Los recordatorios de cita solo se repasan al abrir el programa

El recordatorio T-48h/T-24h estaba escrito como tarea de Celery y **nadie lo
disparaba**: el planificador configurado es el de base de datos
(`django_celery_beat`) y el código no crea ninguna fila de `PeriodicTask`. La
tarea existía, tenía pruebas y no corría nunca —ni en un servidor—.

Ahora hay un comando, y es el que vale para las dos formas de usar SIBU:

    python manage.py recordatorios

Crea los recordatorios que ya tocaba enviar y nadie envió. Es idempotente:
llamarlo dos veces no duplica nada.

- **La portable lo llama en cada arranque.** No hace falta hacer nada.
- **En un servidor va en el cron**, cada hora, que es más simple que levantar
  un `beat` para una tarea:

      0 * * * * cd /opt/sibu && python manage.py recordatorios --silencioso

Con la portable cerrada no se avisa a nadie: es el límite de no tener un
servicio corriendo detrás, y es otra razón para que el SIBU de verdad esté en
una instancia central y las portables sean clientes.

Un detalle que importa en el texto del aviso: el título dice las horas que **de
verdad** faltan, no las de la ventana. Si la portable estuvo cerrada y se abre
a 25 horas de una cita, el aviso pendiente es el de la ventana de 48 —es el que
no se envió—, pero anunciarlo como «en 48h» le adelantaría la cita un día
entero a quien lo lee.

### Modo cliente: cuando la portable abre el SIBU de la Unidad

Con un `portable/servidor.txt` dentro (hay plantilla en
`portable/servidor.txt.example`), la portable no levanta base ninguna: abre el
navegador contra la instancia central. El mismo paquete y el mismo icono
sirven para los dos modos.

La dirección se escribe como la escribiría una persona —`10.0.0.5:8000`,
`sibu.unl.edu.ec`— y el launcher le pone el esquema; sin eso, el navegador
recibía algo que no es una URL y abría una búsqueda.

Antes de abrir el navegador comprueba que el servidor contesta, y si no,
**dice las tres cosas que pueden estar pasando** —la red privada sin conectar,
el servidor apagado, la dirección equivocada— y aclara que no se ha perdido
nada, porque en modo cliente los datos no están en la carpeta. Un «no se puede
conectar» del navegador no distingue entre esas tres.
