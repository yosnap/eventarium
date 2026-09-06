# Imagen de la API. El mismo contenedor sirve para la API, el worker y las migraciones:
# solo cambia el comando. Sin secretos ni ficheros .env dentro (ver .dockerignore).

FROM python:3.12-slim-bookworm AS base

# libmagic1 es obligatorio: python-magic identifica los ficheros subidos por sus bytes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# ---------------------------------------------------------------- dependencias
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /usr/local/bin/uv

WORKDIR /app

# Capa cacheable: las dependencias solo se reinstalan si cambian los lockfiles.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# -------------------------------------------------------------------- runtime
FROM base AS runtime

# Usuario sin privilegios: un proceso comprometido no debe poder escribir en la imagen.
RUN useradd --create-home --uid 10001 aplicacion

WORKDIR /app

COPY --from=builder --chown=aplicacion:aplicacion /app /app

USER aplicacion

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# Worker:      taskiq worker app.core.tasks:broker
# Migraciones: alembic upgrade head
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
