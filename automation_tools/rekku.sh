#!/usr/bin/with-contenv bash
set -e

echo "[99-rekku] Adjusting ownership"

if [ "$(id -u)" = "0" ]; then
    chown -R abc:abc /app /home/rekku /config || true
fi

echo "[99-rekku] Initialization complete"
