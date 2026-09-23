# --- build ---------------------------------------------------------------- #
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Entra values are baked in at build time - Vite inlines VITE_* into the bundle.
ARG VITE_AAD_TENANT_ID=""
ARG VITE_AAD_CLIENT_ID=""
ARG VITE_API_SCOPE=""
ENV VITE_AAD_TENANT_ID=$VITE_AAD_TENANT_ID \
    VITE_AAD_CLIENT_ID=$VITE_AAD_CLIENT_ID \
    VITE_API_SCOPE=$VITE_API_SCOPE

RUN npm run build

# --- serve ---------------------------------------------------------------- #
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY default.conf.template /etc/nginx/templates/default.conf.template

# BFF_URL is substituted into the template by the nginx image's entrypoint.
ENV BFF_URL=http://bff

EXPOSE 8080
