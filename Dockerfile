# syntax=docker/dockerfile:1
FROM node:24-alpine AS frontend

WORKDIR /frontend

COPY web/frontend-react/package*.json ./
RUN npm ci

COPY web/frontend-react ./
RUN npm run build

FROM python:3.12-slim AS python-build

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir uv==0.11.8 \
    && uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENS_NOVEL_ROOT=/app \
    PATH=/app/.venv/bin:$PATH

COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY config ./config
COPY web ./web
COPY --from=python-build /app/.venv ./.venv
COPY --from=frontend /frontend/dist ./web/frontend-react/dist

RUN groupadd --gid 10001 agens \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin agens \
    && mkdir -p /app/runtime /tmp \
    && chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "web.backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
