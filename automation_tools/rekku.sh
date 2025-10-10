#!/usr/bin/with-contenv bash
set -e

echo "[99-synth] Adjusting ownership"

if [ "$(id -u)" = "0" ]; then
    chown -R abc:abc /app /home/synth /config || true
fi

echo "[99-synth] Initialization complete"
