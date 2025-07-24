#!/usr/bin/with-contenv bash
set -e

USER_NAME="${CUSTOM_USER:-rekku}"
echo "[99-rekku] Adjusting ownership for $USER_NAME"

if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 /app /home/rekku /config || true
fi

echo "[99-rekku] Init complete"
