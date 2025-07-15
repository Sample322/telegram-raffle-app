# Build stage
FROM node:18-alpine as build

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm ci

# Copy source code
COPY . .

# Build the app with environment variables
ARG REACT_APP_API_URL
ARG REACT_APP_WS_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ENV REACT_APP_WS_URL=$REACT_APP_WS_URL

RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx config if exists
COPY nginx.conf /etc/nginx/conf.d/default.conf 2>/dev/null || true

# Add a default nginx config if none exists
RUN if [ ! -f /etc/nginx/conf.d/default.conf ]; then \
    echo 'server { \
        listen 80; \
        server_name localhost; \
        root /usr/share/nginx/html; \
        index index.html; \
        location / { \
            try_files $uri $uri/ /index.html; \
        } \
    }' > /etc/nginx/conf.d/default.conf; \
    fi

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]