FROM node:18-alpine as builder

WORKDIR /app

# Копируем package files
COPY package*.json ./

# Устанавливаем зависимости
RUN npm ci --only=production

# Копируем исходники
COPY . .

# Собираем приложение
RUN npm run build

# Финальная стадия - просто копируем build
FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/build ./build

# Команда для копирования build в volume
CMD ["sh", "-c", "cp -r /app/build/* /app/build/"]