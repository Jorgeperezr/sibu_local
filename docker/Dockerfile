FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Dependencias de sistema para WeasyPrint (PDF) y psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libpango-1.0-0 libpangoft2-1.0-0 \
    libcairo2 libgdk-pixbuf-2.0-0 shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .
# Sin `|| true`. Lo llevaba, y eso convertía un fallo de construcción visible en
# un fallo de producción invisible: `CompressedManifestStaticFilesStorage` aborta
# si un archivo referencia algo que no está —pasó con el sourcemap de Bootstrap—,
# la imagen se construía igual y el sitio arrancaba sin estáticos, con cada
# página lanzando un ValueError por el manifiesto ausente.
#
# `collectstatic` no toca la base de datos, pero SÍ importa los ajustes, así que
# necesita valores para construir. Van EN LA PROPIA ORDEN y no en un `ENV`: un
# `ENV` se queda en la imagen, y entonces olvidar `SECRET_KEY` en `.env.prod` no
# daría error —arrancaría con la clave de relleno, en silencio—. Así, si falta,
# el contenedor no levanta.
RUN SECRET_KEY=solo-para-construir-la-imagen-no-se-usa-al-ejecutar-0123456789 \
    ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgres://sibu:sibu@db:5432/sibu \
    python manage.py collectstatic --noinput --settings=config.settings.prod

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
