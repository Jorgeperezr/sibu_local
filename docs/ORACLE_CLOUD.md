# Desplegar SIBU en Oracle Cloud (capa gratuita)

Guía concreta para el servidor gratuito de Oracle. El procedimiento general
está en `DESPLIEGUE.md`; esto cubre lo que es propio de Oracle y las tres
trampas que hacen perder una tarde.

Todo lo de aquí se probó de punta a punta antes de escribirlo —gunicorn detrás
de nginx con TLS, login por HTTPS, estáticos con manifiesto y las cabeceras de
seguridad—, salvo lo que depende del dominio real, que se señala.

## 1. Qué máquina pedir

Oracle regala dos cosas distintas y la diferencia importa:

| | AMD «micro» | **ARM Ampere A1** |
|---|---|---|
| Núcleos / RAM | 1 / 1 GB | hasta 4 / 24 GB |
| Sirve para SIBU | justo | **sí, con holgura** |

**Pida la ARM Ampere.** SIBU levanta PostgreSQL, gunicorn y nginx, y la carga
de la base institucional lee un Excel de miles de filas con pandas: 1 GB se
queda corto y el proceso muere sin explicación (el núcleo lo mata por memoria y
en el registro solo queda un *worker* que desapareció).

Si solo consigue la AMD de 1 GB —Oracle a veces no tiene capacidad ARM—,
**añada intercambio antes de nada** o la primera carga de datos tumbará el
servidor:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Imagen: **Ubuntu 22.04 o 24.04**. Disco: 50 GB del bloque gratuito.

## 2. La trampa de Oracle: hay DOS cortafuegos

Es lo que hace perder la tarde. Abrir el puerto en la consola de Oracle **no
basta**: la imagen de Ubuntu de Oracle trae además reglas locales de `iptables`
que descartan todo menos SSH. Se abre en los dos sitios o el navegador se queda
esperando para siempre, sin error que leer.

**a) En la consola de Oracle** — Redes → *Virtual Cloud Network* → subred →
*Security List* → reglas de entrada:

| Origen | Protocolo | Puerto |
|---|---|---|
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

**b) En la propia máquina**, por SSH:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save     # si no, se pierden al reiniciar
```

Compruebe que quedaron: `sudo iptables -L INPUT -n --line-numbers | head`.

## 3. Preparar la máquina

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
git clone <url-del-repositorio> sibu && cd sibu
```

## 4. Configurar

```bash
cp .env.prod.example .env.prod
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # SECRET_KEY
nano .env.prod
```

Lo que no puede fallar:

- `ALLOWED_HOSTS` con el dominio real. Si queda en blanco, Django responde
  **400 a todo**.
- `CSRF_TRUSTED_ORIGINS` con **el mismo dominio y con `https://` delante**.
  Este es el error que más caro sale: el sitio arranca, todas las páginas
  responden 200 y **nadie puede iniciar sesión**, porque el 403 solo aparece al
  enviar el primer formulario. `check --deploy` lo avisa (sibu.E020/E021/E022)
  y el compose lo ejecuta antes de servir.
- `POSTGRES_PASSWORD`, o el contenedor de la base no arranca.
- `EMAIL_HOST` y sus credenciales: sin SMTP **nadie puede vincular su cuenta
  en el portal**, porque el código de verificación viaja al correo
  institucional y esa es la prueba de identidad.

## 5. Certificado TLS

Necesita un dominio apuntando a la IP pública de la máquina. Con el dominio ya
resuelto:

```bash
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d sibu.unl.edu.ec   # con el 80 libre
mkdir -p docker/certs
sudo cp /etc/letsencrypt/live/sibu.unl.edu.ec/fullchain.pem docker/certs/
sudo cp /etc/letsencrypt/live/sibu.unl.edu.ec/privkey.pem  docker/certs/
sudo chown $USER docker/certs/*.pem
```

Sin dominio todavía, para probar, sirve un certificado propio —el navegador
avisará de que no es de confianza, y es correcto que avise—:

```bash
mkdir -p docker/certs
openssl req -x509 -newkey rsa:2048 -nodes -days 90 \
  -keyout docker/certs/privkey.pem -out docker/certs/fullchain.pem \
  -subj "/CN=$(curl -s ifconfig.me)"
```

## 6. Levantar

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f web
```

El arranque hace, en este orden: `check --deploy` (y **aborta** si la
configuración no está), `migrate` y `preparar`. Que aborte es lo que se quiere:
un error de configuración solo sale barato antes de que entre nadie.

## 6.1 La primera cuenta

`preparar` deja servicios, roles y catálogos, pero **ninguna persona**: en
producción no se siembran las cuentas de demostración, que llevan contraseñas
conocidas. Sin este paso el sistema está en pie y no puede entrar nadie.

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec web \
  python manage.py createsuperuser
```

Después, desde esa cuenta, se dan de alta los profesionales con su servicio: es
el servicio el que decide qué ve cada uno.

## 7. Comprobar que de verdad funciona

Que la portada cargue no prueba casi nada: con `CSRF_TRUSTED_ORIGINS` mal
puesto **la portada carga igual**. Hay que enviar un formulario:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec web \
  python manage.py ensayo_despliegue --usuario admin --clave '…'
```

Sin `--usuario` y `--clave` el ensayo abre las páginas y comprueba el
manifiesto de estáticos, pero **no ejercita el acceso** y lo dice: ahí es donde
aparece el 403 de CSRF, así que un ensayo sin credenciales no da por bueno un
despliegue.

Y a mano, desde el navegador:

1. Entrar con una cuenta y **cerrar sesión** (el cierre va por POST).
2. Abrir un expediente y **guardar** algo.
3. Descargar un PDF —el informe estadístico— para comprobar WeasyPrint.
4. Subir un archivo pequeño en un taller, para el volumen de `media`.

## 8. Después

- **Copias de la base**, y probadas restaurando. Una copia que nunca se
  restauró no es una copia.
  ```bash
  docker compose --env-file .env.prod -f docker-compose.prod.yml exec db \
    pg_dump -U sibu sibu | gzip > respaldo-$(date +%F).sql.gz
  ```
- **Renovar el certificado**: `sudo certbot renew` y volver a copiar los `.pem`
  a `docker/certs/`, luego `docker compose ... restart proxy`.
- `docker compose --env-file .env.prod -f docker-compose.prod.yml exec web python manage.py revisar_datos --detalle`
  de vez en cuando: busca incoherencias que ninguna restricción puede ver.

## Si algo va mal

| Síntoma | Causa casi segura |
|---|---|
| El navegador se queda esperando | El `iptables` de la máquina (§2b) |
| `400 Bad Request` en todo | `ALLOWED_HOSTS` sin el dominio |
| Se ve todo pero el login da 403 | `CSRF_TRUSTED_ORIGINS` (§4) |
| Bucle de redirección | Falta `X-Forwarded-Proto` en el proxy |
| Las páginas salen sin estilos | `collectstatic` falló al construir |
| Un *worker* muere sin más | Memoria: use la ARM o añada swap (§1) |
| «POSTGRES_PASSWORD is not set» aunque está en `.env.prod` | Falta `--env-file .env.prod` en la orden (§6) |
