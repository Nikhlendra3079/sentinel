FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml .
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
RUN pip install --upgrade pip && pip install .

EXPOSE 8000
# Set SENTINEL_UVICORN_WORKERS to exercise independent worker processes.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${SENTINEL_UVICORN_WORKERS:-1}"]
