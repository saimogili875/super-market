# FreshMart — Supermarket & Grocery Ordering Platform

Django 5.x foundation scaffold — ASGI-ready, PostgreSQL 16, Redis 7. Real-time grocery delivery, in-store pickup, agent dispatch, and admin operations.

## Running on Postgres
1. Start backing services (Docker Desktop required):
```bash
docker compose up -d           # postgres + redis
```

## Local Setup

```bash
# 1. Configure environment
cp .env.example .env          # edit SECRET_KEY and other values

# 2. Install Python dependencies (use a virtualenv)
pip install -r requirements/dev.txt

# 4. Apply database migrations
python manage.py migrate

# 4. Run the dev server (worker count pinned to the 2-vCPU box; workers are the main RAM cost)
uvicorn config.asgi:application --workers 2
# Visit http://127.0.0.1:8000/healthz
```

## Quality Checks

```bash
pytest                         # run test suite
ruff check .                   # lint
ruff format --check .          # format check
pip-audit -r requirements/base.txt  # dependency audit
```

## Project Structure

```
restaurant/
├── config/          # Django project package (settings, urls, asgi/wsgi)
│   └── settings/    # base → dev / prod split
├── apps/
│   └── core/        # shared base models, healthz view
├── requirements/    # base.txt + dev.txt
└── docker-compose.yml  # postgres + redis for local dev
```
