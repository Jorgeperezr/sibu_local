# Despliegue de SIBU

La lista ejecutable está en `apps/core/checks.py` y corre con
`python manage.py check --deploy`. Este documento cubre lo que el código **no
puede verificar por sí mismo**.

## 1. Antes de tocar el servidor

- [ ] Los sprints pendientes están mergeados en `main` **en orden**.
- [ ] `bash scripts/diagnostico.sh` no reporta tarballs versionados.
- [ ] El CI de `main` está en verde y ese verde es real (ver §7).

## 2. Infraestructura

- [ ] PostgreSQL 16 con copias de seguridad **probadas restaurando**, no solo
      programadas. Una copia que nunca se restauró no es una copia.
- [ ] Volumen persistente para `MEDIA_ROOT` (evidencias de talleres, PDFs) y
      para `LOG_FILE`. Nunca bajo `/tmp`.
- [ ] Redis para Celery (recordatorios de citas).
- [ ] Certificado TLS y proxy inverso con `X-Forwarded-Proto`.
- [ ] Zona horaria del servidor coherente con `America/Guayaquil`. Los bugs de
      fecha de este proyecto salieron todos de aquí.

## 3. Configuración

- [ ] `.env` a partir de `.env.example`, con `SECRET_KEY` nueva.
- [ ] `python manage.py check --deploy --fail-level WARNING` sin errores.
- [ ] **`python manage.py revisar_datos --detalle` ANTES de migrar.** Estas
      migraciones traen restricciones que fallan si los datos que ya están en
      el servidor las violan: un lote en negativo, una cédula mal digitada, una
      agenda invertida, dos fichas socioeconómicas vigentes. Ver el informe
      antes cuesta un minuto; ver fallar la migración a mitad, bastante más.
      Devuelve código 1 si encuentra algo, así que se puede encadenar.
- [ ] `python manage.py migrate` y `collectstatic`.
- [ ] `python manage.py preparar --sin-demo`, que hace `seed_inicial`,
      `configurar_rbac` y el catálogo CIE-10 en el orden correcto. Los datos de
      demostración se omiten solos con `DEBUG=False`; el comando `datos_demo`
      además se niega a correr, porque trae contraseñas conocidas y pacientes
      inventados dentro del expediente único.
- [ ] `python manage.py revisar_datos` otra vez, ya migrado: debe salir limpio.

## 4. Correo — bloquea el portal

Sin SMTP funcionando, la vinculación de cuentas no envía el código y **el
portal queda inservible en silencio**: el usuario ve un mensaje de éxito y nunca
recibe nada.

- [ ] Enviar un correo de prueba real desde `manage.py shell`.
- [ ] Confirmar que los correos institucionales constan en el dato académico:
      sin ellos, cada vinculación debe hacerse presencialmente.

## 5. Firma electrónica — opcional

Se despliega con `FIRMA_PROVIDER=deshabilitada` y el sistema funciona. Para
activarla hace falta **gestión institucional, no desarrollo**:

- [ ] Términos y Condiciones del MINTEL aceptados.
- [ ] **Administrador Institucional de FirmaEC (AIF)** delegado por oficio de la
      máxima autoridad.
- [ ] Callback publicado en **443 con subdominio y SSL**.
- [ ] Registro del sistema ante el MINTEL con informe de pruebas. Sin registro,
      FirmaEC advierte al usuario de un "potencial riesgo de seguridad".
- [ ] Decidir `FIRMAEC_DESCENTRALIZADO_PROPIO`. En `True`, los informes de
      Psicología pueden salir hacia el firmador: **solo si corre en
      infraestructura de la UNL**.

## 6. Verificación funcional en el servidor

- [ ] Iniciar sesión con cada rol y confirmar que ve lo suyo y nada más.
- [ ] **El sello de Psicología**: con una cuenta de Dirección, intentar abrir
      una ficha psicológica por URL directa. Debe dar 403.
- [ ] Vincular una cuenta del portal de principio a fin, con correo real.
- [ ] Agendar y cancelar una cita desde el portal.
- [ ] Adjuntar una evidencia a un taller y comprobar que persiste tras
      reiniciar el servicio.
- [ ] Abrir `/reportes/` con un rol directivo y con uno que no lo sea.

## 7. Sobre el CI en verde

Un CI en verde solo significa algo si el fix de ruff de los Sprints 1–4 está
realmente aplicado. Si en su día se commiteó el `.tar.gz` en lugar de
extraerlo, el CI puede estar reportando sobre un árbol que no incluye las
correcciones. `scripts/diagnostico.sh` lo detecta en su sección 2.

## 8. Antes del piloto

- [ ] Definir la retención de `LogAuditoria`: es evidencia, no un log rotativo.
- [ ] Acordar el procedimiento de acceso de emergencia (break-glass) para los
      servicios **no** confidenciales, y dejar por escrito que Psicología no lo
      admite.
- [ ] Capacitar al personal en que la firma puede estar deshabilitada y qué
      significa un documento sin firmar.
- [ ] Pruebas de carga sobre la agenda: es el punto de contención (reservas
      concurrentes sobre el mismo turno).
