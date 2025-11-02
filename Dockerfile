FROM python:3.11-slim

# Установка системных зависимостей для PostgreSQL
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
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

# Запускаем из src/main.py
CMD ["python", "src/main.py"]