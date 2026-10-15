# ---------- build stage ----------
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

# ---------- runtime stage ----------
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --no-create-home appuser

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

# Run collectstatic as root using prod settings (dummy DB for build only)
RUN DATABASE_URL=sqlite:////tmp/build.db \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    SECRET_KEY=build-only-secret \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput && \
    chmod +x start.sh && \
    chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

CMD ["sh", "start.sh"]
