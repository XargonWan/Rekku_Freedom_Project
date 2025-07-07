#!/bin/bash
set -e

echo "[START] Running as $(whoami)"

# Fix permessi se siamo root
if [ "$(id -u)" = "0" ]; then
  echo "[FIX] Chown dinamico a rekku su /app e /home/rekku"
  chown -R rekku:rekku /app /home/rekku || echo "[WARN] chown fallito"
fi

cd /app
exec python3 main.py
