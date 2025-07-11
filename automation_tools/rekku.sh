#!/usr/bin/with-contenv bash
set -e

echo "[99-rekku] Adjusting ownership"

if [ "$(id -u)" = "0" ]; then
    chown -R abc:abc /app /home/rekku || true
fi

echo "[99-rekku] Starting Rekku Freedom Project"
s6-setuidgid abc /app/rekku.sh run --as-service &
