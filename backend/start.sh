#!/bin/bash
set -e

echo "Running migrations..."
alembic -c alembic.ini upgrade head

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000