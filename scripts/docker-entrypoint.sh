#!/bin/sh
set -eu

if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    rm -f "$PROMETHEUS_MULTIPROC_DIR"/*
fi

alembic upgrade head
exec uvicorn app.main:app \\
    --host 0.0.0.0 \\
    --port 8000 \\
    --workers "${SENTINEL_UVICORN_WORKERS:-1}"
