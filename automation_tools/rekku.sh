#!/usr/bin/with-contenv bash
set -e

echo "[99-rekku] Starting Rekku bot as user rekku"

if [ "$(id -u)" = "0" ]; then
    chown -R rekku:rekku /app /home/rekku || true
fi

s6-setuidgid rekku python3 /app/main.py &
