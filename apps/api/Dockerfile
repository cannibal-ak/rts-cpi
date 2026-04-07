FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ── Dev target: uvicorn with reload (migrations run via entrypoint) ──
FROM base AS dev
CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

# ── Prod target: gunicorn + uvicorn workers ──
FROM base AS prod
RUN pip install --no-cache-dir gunicorn
CMD ["bash", "-c", "alembic upgrade head && gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000"]
