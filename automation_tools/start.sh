#!/bin/bash
set -e

echo "[99-rekku.sh] Running as $(whoami)"

# Fix permissions if executed by root
if [ "$(id -u)" = "0" ]; then
  echo "[99-rekku.sh] Setting ownership on /app and /home/rekku"
  chown -R rekku:rekku /app /home/rekku || echo "[99-rekku.sh] chown failed"
fi

cd /app
su -s /bin/bash rekku -c "python3 /app/main.py" &

