FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Instalamos dependencias necesarias para psycopg2 (PostgreSQL) y herramientas de red
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Recopilar archivos estáticos para la entrega eficiente en producción por WhiteNoise
RUN python manage.py collectstatic --noinput

# Render o ambientes Cloud pueden usar puertos dinámicos asignados por la variable de entorno PORT.
# Si no está definida la variable PORT, se establece un fallback al puerto 8000.
EXPOSE 8000

CMD python manage.py migrate && \
    python manage.py shell -c "import os; from django.contrib.auth import get_user_model; User = get_user_model(); u = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'); e = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com'); p = os.environ.get('DJANGO_SUPERUSER_PASSWORD'); p and (User.objects.filter(username=u).exists() or User.objects.create_superuser(u, e, p))" && \
    gunicorn core.wsgi:application --bind 0.0.0.0:${PORT:-8000}