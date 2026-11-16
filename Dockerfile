# Генератор КП: Flask + gunicorn, PDF через WeasyPrint.
# Собирается под arm64 (сервер Hetzner CAX21 и Mac) и amd64 без правок.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    KP_OUTPUT_DIR=/app/data/output

# Pango и HarfBuzz нужны WeasyPrint. Шрифты лежат в проекте, системные не нужны.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 tzdata \
    && rm -rf /var/lib/apt/lists/*

# uid владельца примонтированного data/ на сервере
ARG APP_UID=1000
RUN useradd --uid ${APP_UID} --create-home app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app . .
RUN mkdir -p /app/data/output && chown -R app:app /app/data

USER app
EXPOSE 8000

# Генерация КП идет 20–40 секунд, отсюда длинный timeout
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "app:app"]
