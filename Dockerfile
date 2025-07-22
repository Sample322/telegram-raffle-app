# Build stage
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

# Копируем билд React приложения
COPY --from=build /app/build /usr/share/nginx/html

# Создаем nginx конфиг прямо в Dockerfile
RUN echo 'server { \n\
    listen 80; \n\
    server_name _; \n\
    \n\
    root /usr/share/nginx/html; \n\
    index index.html; \n\
    \n\
    # Размер загружаемых файлов \n\
    client_max_body_size 20M; \n\
    \n\
    # Health check для Timeweb \n\
    location /health { \n\
        access_log off; \n\
        return 200 "healthy"; \n\
        add_header Content-Type text/plain; \n\
    } \n\
    \n\
    # API проксирование \n\
    location /api/ { \n\
        proxy_pass http://backend:8000/api/; \n\
        proxy_http_version 1.1; \n\
        proxy_set_header Upgrade $http_upgrade; \n\
        proxy_set_header Connection "upgrade"; \n\
        proxy_set_header Host $host; \n\
        proxy_set_header X-Real-IP $remote_addr; \n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \n\
        proxy_set_header X-Forwarded-Proto $scheme; \n\
        proxy_cache_bypass $http_upgrade; \n\
    } \n\
    \n\
    # WebSocket для розыгрышей \n\
    location /api/ws/ { \n\
        proxy_pass http://backend:8000/api/ws/; \n\
        proxy_http_version 1.1; \n\
        proxy_set_header Upgrade $http_upgrade; \n\
        proxy_set_header Connection "upgrade"; \n\
        proxy_set_header Host $host; \n\
        proxy_set_header X-Real-IP $remote_addr; \n\
        proxy_read_timeout 86400; \n\
    } \n\
    \n\
    # Загрузки \n\
    location /uploads/ { \n\
        proxy_pass http://backend:8000/uploads/; \n\
    } \n\
    \n\
    # Frontend SPA \n\
    location / { \n\
        try_files $uri $uri/ /index.html; \n\
        \n\
        # Отключаем кеш для index.html \n\
        location = /index.html { \n\
            add_header Cache-Control "no-cache, no-store, must-revalidate"; \n\
        } \n\
    } \n\
}' > /etc/nginx/conf.d/default.conf

# Удаляем дефолтный конфиг nginx
RUN rm -f /etc/nginx/conf.d/default.conf.bak

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]