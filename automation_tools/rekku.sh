#!/usr/bin/with-contenv bash
set -e

echo "[99-rekku] Starting Rekku bot as user abc"

if [ "$(id -u)" = "0" ]; then
    chown -R abc:abc /app /home/rekku || true
fi

s6-setuidgid abc python3 /app/main.py &
