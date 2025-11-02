FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя приложения
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всей структуры проекта
COPY . .

# Создание директорий для данных и логов
RUN mkdir -p logs data backups && \
    chown -R app:app /app

USER app

# Переменные окружения
ENV PYTHONPATH=/app/src:/app
ENV PYTHONUNBUFFERED=1

# Health check (если нужно, можно временно отключить)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Запускаем из src/main.py
CMD ["python", "src/main.py"]