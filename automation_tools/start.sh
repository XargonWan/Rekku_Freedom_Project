#!/bin/bash
set -e

echo "[start.sh] Running as $(whoami)"

# Fix permissions if executed by root
if [ "$(id -u)" = "0" ]; then
  echo "[start.sh] Setting ownership on /app and /home/rekku"
  chown -R rekku:rekku /app /home/rekku || echo "[start.sh] chown failed"
fi

cd /app
echo "[start.sh] Rekku main.py started..."
python3 /app/main.py &

