FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# — системные пакеты (curl для healthcheck)
RUN apt-get update && apt-get install -y gcc postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

# — Python зависимости
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install boto3

# — исходники приложения
COPY . .

# — каталог для временных загрузок (если нужен)
RUN mkdir -p uploads

EXPOSE 8000

# Healthcheck из самого контейнера (дублирует compose)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
