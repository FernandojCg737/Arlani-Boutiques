FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
# El modelo (~118 MB) y el tokenizador se descargan al construir la imagen, no en cada arranque.
RUN python -c "from app import cargar; cargar()"

EXPOSE 8000
# Render inyecta $PORT; un solo proceso para no duplicar el modelo en memoria.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
