# Cómo aplicar el Sprint 3 al proyecto

Este sprint se distribuye ahora como **git bundle** además del `.tar.gz`
tradicional. Elige el método que prefieras.

## Opción A — Git bundle (recomendado, preserva historial)

```bash
cd ~/Developer/sibu

# 1. Traer los commits del sprint
git fetch ~/Downloads/sibu_sprint3_citas.bundle sprint/03-citas:sprint/03-citas
git checkout sprint/03-citas

# 2. Aplicar migraciones y probar
python manage.py migrate
pytest apps/citas -q

# 3. Push al remoto y PR
git push -u origin sprint/03-citas
# Abrir PR en GitHub hacia main
```

## Opción B — Tar.gz (drop-in sin historial)

```bash
cd ~/Developer/sibu
tar -xzf ~/Downloads/sibu_sprint3_citas.tar.gz
rm ~/Downloads/sibu_sprint3_citas.tar.gz

python manage.py makemigrations
python manage.py migrate
pytest apps/citas -q

git checkout -b sprint/03-citas
git add -A
git commit -m "feat: sprint 3 — módulo citas (agenda y ciclo de vida)"
git push -u origin sprint/03-citas
```

## Uso rápido
1. Crear un profesional en `/admin/` (o usar `createsuperuser`) y asignarle un servicio.
2. Crear una agenda: admin → Citas → Agendas → Añadir.
3. Ir a `/citas/reservar/`, buscar una cédula (previamente cargada en S1)
   y agendar una cita seleccionando servicio/profesional/fecha/turno.
4. En `/citas/` se ve la agenda del día y se pueden cambiar estados.
