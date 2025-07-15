# syntax=docker/dockerfile:1.6

###############################################################################
# ⛏  Build stage – compile the React application
###############################################################################
FROM node:18.20.2-alpine AS build    

WORKDIR /app

# 1️⃣  Install dependencies (this layer is reused if package*.json unchanged)
COPY package*.json ./
RUN npm ci --omit=dev

# 2️⃣  Copy application sources
COPY . .

# 3️⃣  Build with environment variables baked in
ARG REACT_APP_API_URL
ARG REACT_APP_WS_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL \
    REACT_APP_WS_URL=$REACT_APP_WS_URL

RUN npm run build


###############################################################################
# 🚀  Runtime stage – serve the static files with NGINX
###############################################################################
FROM nginx:1.27-alpine            

# 1️⃣  Copy the compiled artefacts
COPY --from=build /app/build /usr/share/nginx/html

# 2️⃣  Provide a minimal default config
#     (If you want a custom nginx.conf, mount or COPY it at build time
#      and overwrite /etc/nginx/conf.d/default.conf)
RUN printf 'server {\n\
    listen 80;\n\
    server_name localhost;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

# 3️⃣  Drop privileges – run as the nginx user instead of root
USER nginx

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
