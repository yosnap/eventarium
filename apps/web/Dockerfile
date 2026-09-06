# Imagen del frontend: build de Angular + servidor SSR en Node.
# Sin secretos ni ficheros .env dentro (ver .dockerignore).

FROM node:22-alpine AS builder

RUN corepack enable

WORKDIR /app

# Capa cacheable: las dependencias solo se reinstalan si cambian los lockfiles.
# pnpm-workspace.yaml lleva los ajustes de instalación (ver el fichero).
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm exec ng build

# -------------------------------------------------------------------- runtime
FROM node:22-alpine AS runtime

ENV NODE_ENV=production \
    PORT=4000

# Usuario sin privilegios: la imagen de node trae `node` (uid 1000).
WORKDIR /app

COPY --from=builder --chown=node:node /app/dist/web ./dist/web

USER node

EXPOSE 4000

# Variables esperadas en tiempo de ejecución:
#   API_INTERNAL_URL   URL de la API en la red interna (por defecto http://api:8000)
#   NG_ALLOWED_HOSTS   dominios permitidos, separados por comas; sin definir, cualquiera
#                      (la validación real la hacen Caddy y la resolución por host de la API)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://localhost:4000/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "dist/web/server/server.mjs"]
