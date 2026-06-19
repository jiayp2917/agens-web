FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    AGENS_NOVEL_ROOT=/app \
    AGENS_WEB_DB=/app/runtime/web/agens_web.sqlite3

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY config ./config
COPY src ./src
COPY web ./web
COPY deploy/docker-entrypoint.sh /usr/local/bin/agens-web-entrypoint.sh

RUN chmod +x /usr/local/bin/agens-web-entrypoint.sh \
    && pip install --no-cache-dir --no-deps -e .

EXPOSE 8000

ENTRYPOINT ["agens-web-entrypoint.sh"]

