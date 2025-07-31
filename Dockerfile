# Build stage
FROM node:18-alpine as build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install ALL dependencies
RUN npm install

# Copy all source files
COPY . .

# Build the application
RUN npm run build

# Проверка что build создался
RUN ls -la /app/build && \
    echo "Build size:" && \
    du -sh /app/build

# Production stage
FROM nginx:alpine

# Copy built React app
COPY --from=build /app/build /usr/share/nginx/html

# Проверка что файлы скопировались
RUN ls -la /usr/share/nginx/html && \
    echo "HTML size:" && \
    du -sh /usr/share/nginx/html