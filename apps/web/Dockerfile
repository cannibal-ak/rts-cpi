# ───────────────────────────────────────────────
# RTS CPI Web — Multi-stage Dockerfile
# ───────────────────────────────────────────────
# Stage 1 — deps: install node_modules
# Stage 2 — build: production bundle
# Stage 3 — prod : lightweight nginx serving static files
# ───────────────────────────────────────────────

# ── Stage 1: dependency install ──────────────────
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json ./
# Install build essentials if needed for some native dependencies, 
# though for this project npm install usually works on slim.
RUN npm install --legacy-peer-deps

# ── Stage 4: development ─────────────────────────
FROM node:20-slim AS dev
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]

# ── Stage 2: production build ────────────────────
FROM node:20-slim AS build

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package.json ./
COPY . .

# Build-time environment variables
ARG VITE_API_BASE_URL
ARG VITE_TENANT_ID
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_TENANT_ID=$VITE_TENANT_ID
ARG VITE_SUPERSET_URL
ENV VITE_SUPERSET_URL=$VITE_SUPERSET_URL

RUN npx vite build

# ── Stage 3: production serve (nginx) ────────────
FROM nginx:1.25-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

