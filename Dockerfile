FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Instalamos dependencias necesarias para psycopg2 (PostgreSQL)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Render usa el puerto 10000 por defecto para servicios web
EXPOSE 10000

# Usamos gunicorn para producción en lugar del runserver de Django
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:10000"]