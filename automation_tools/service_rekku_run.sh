#!/usr/bin/with-contenv bash
set -euo pipefail

USER_NAME="${CUSTOM_USER:-rekku}"
LOG_FILE="/config/logs/rekku_backend.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Forward output to both stdout and a persistent log file for debugging
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[rekku service] starting as $USER_NAME"
exec s6-setuidgid "$USER_NAME" /app/rekku.sh run --as-service
