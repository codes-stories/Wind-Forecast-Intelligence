# Build stage: compile the static dashboard
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# API base URL is injected at build time. "same-origin" (default) = requests
# stay on this origin and nginx proxies /api + /health to the backend.
# For a static deploy set the public backend URL, e.g.
#   --build-arg VITE_API_BASE=https://your-backend.onrender.com
ARG VITE_API_BASE="same-origin"
ENV VITE_API_BASE=${VITE_API_BASE}

RUN npm run build

# Serve stage: nginx serves the SPA and proxies /api + /health to the backend
FROM nginx:1.27-alpine

ENV BACKEND_URL=http://backend:8000

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1/health" || exit 1

# nginx-entrypoint renders the template with $BACKEND_URL, then starts nginx
CMD ["nginx", "-g", "daemon off;"]
