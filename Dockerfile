FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Устанавливаем PM2
RUN npm install -g pm2

CMD ["pm2-runtime", "main.py", "--name", "trading-bot"]