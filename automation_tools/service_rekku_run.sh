#!/usr/bin/with-contenv bash
set -euo pipefail

USER_NAME="${CUSTOM_USER:-rekku}"
echo "[rekku service] starting as $USER_NAME" >&2
exec s6-setuidgid "$USER_NAME" /app/rekku.sh run --as-service
