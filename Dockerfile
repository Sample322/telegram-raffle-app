# Build stage
FROM node:18-alpine as build

# Install build dependencies
RUN apk add --no-cache python3 make g++

WORKDIR /app

# Copy package files for better caching
COPY package*.json ./
COPY yarn.lock* ./

# Install dependencies
RUN npm ci --only=production --silent
RUN npm install --only=development --silent

# Copy all source files
COPY . .

# Set build arguments for environment variables
ARG REACT_APP_API_URL
ARG REACT_APP_WS_URL

# Set environment variables for build
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ENV REACT_APP_WS_URL=$REACT_APP_WS_URL
ENV NODE_ENV=production
ENV GENERATE_SOURCEMAP=false

# Build the application with optimizations
RUN npm run build

# Production stage
FROM nginx:stable-alpine

# Install additional tools
RUN apk add --no-cache curl

# Remove default nginx config
RUN rm -rf /etc/nginx/conf.d/*

# Copy custom nginx configuration
COPY --from=build /app/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built React app
COPY --from=build /app/build /usr/share/nginx/html

# Add health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost/ || exit 1

# Set proper permissions (nginx user already exists in nginx:alpine image)
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]