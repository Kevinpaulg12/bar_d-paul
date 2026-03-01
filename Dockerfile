# 1. Usar una imagen de Python ligera
FROM python:3.11-slim

# 2. Configurar variables de entorno para que Python no genere archivos .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# 4. Instalar dependencias del sistema (necesarias para PostgreSQL y herramientas de red)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 5. Instalar las dependencias de Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiar todo el código del proyecto al contenedor
COPY . /app/

# 7. Exponer el puerto donde corre Django
EXPOSE 8000

# 8. Comando para arrancar la aplicación
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]