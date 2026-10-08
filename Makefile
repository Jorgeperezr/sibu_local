.PHONY: install migrate run up preparar revisar cuentas worker perfil demo seed setup test lint fmt help

help:         ## Mostrar esta ayuda
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:      ## Instalar dependencias de desarrollo
	pip install -r requirements/dev.txt

migrate:      ## Aplicar migraciones
	python manage.py migrate

run:          ## Servidor de desarrollo (sin derivar variables de Codespaces)
	python manage.py runserver 0.0.0.0:8000

up:           ## ARRANQUE. Prepara la base si hace falta y levanta el servidor
	bash scripts/dev.sh

preparar:     ## Migraciones + datos base + RBAC + CIE-10 + cuentas de prueba
	python manage.py preparar

revisar:      ## Buscar incoherencias en los datos ya guardados (no corrige)
	python manage.py revisar_datos --detalle

cuentas:      ## Recordar con qué usuario y contraseña iniciar sesión
	python manage.py cuentas

worker:       ## Worker + beat de Celery
	celery -A config worker -B -l info

seed:         ## Cargar datos base (secciones, servicios, roles)
	python manage.py seed_inicial

perfil:       ## Dar al superusuario un perfil de dev con todos los servicios
	python manage.py perfil_dev

demo:         ## Sembrar usuarios, pacientes y actividad para probar el sistema
	python manage.py datos_demo

setup:        ## Alias de 'preparar' (se conserva por costumbre)
	python manage.py preparar

test:         ## Ejecutar pruebas con cobertura
	pytest --cov=apps

lint:         ## Ruff + bandit (separados: el && oculta el fallo de format)
	ruff check .
	ruff format --check .
	bandit -r apps config -ll

fmt:          ## Formatear con ruff
	ruff format .
	ruff check --fix .
