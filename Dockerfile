FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект включая src
COPY . .

# Устанавливаем src в PYTHONPATH
ENV PYTHONPATH=/app/src

RUN useradd -m -r trader && \
    chown -R trader:trader /app
USER trader

# Запускаем из src
CMD ["python", "-u", "src/main.py"]