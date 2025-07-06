#!/usr/bin/env bash

echo "[init] Starting Rekku bot..."
source /app/.env
exec /app/venv/bin/python3 /app/main.oy
