FROM python:3.11-slim

WORKDIR /app

# Логирование для отладки
RUN echo "Starting backend build..."

# Системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Приложение
COPY . .

# Создаем папку uploads
RUN mkdir -p uploads

EXPOSE 8000

# Проверка установки
RUN python -c "import fastapi; print('FastAPI installed')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]