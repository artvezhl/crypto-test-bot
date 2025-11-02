FROM python:3.11

# Установка пользователя
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

# Установка системных зависимостей для psycopg2
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Установка Python зависимостей
RUN pip install psycopg2-binary python-dotenv

# Переключаемся на пользователя vscode
USER $USERNAME

WORKDIR /app

CMD ["sleep", "infinity"]