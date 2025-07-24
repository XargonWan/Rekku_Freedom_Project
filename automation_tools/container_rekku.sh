#!/usr/bin/with-contenv bash
set -euo pipefail

log() { echo "[rekku.sh] $*"; }

log "Launcher invoked: $*"

cd /app
ENV_FILE="/app/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

PYTHON="/app/venv/bin/python"

MODE="${1:-run}"
shift || true

case "$MODE" in
    run)
        if [ "${1:-}" = "--as-service" ]; then
            shift
            log "Running main.py in service mode"
            exec "$PYTHON" /app/main.py --service "$@"
        else
            log "Running main.py interactively"
            exec "$PYTHON" /app/main.py "$@"
        fi
        ;;
    notify)
        log "Sending test notification"
        python3 - <<'PY'
import asyncio
from telegram import Bot
from core.config import BOT_TOKEN, OWNER_ID
async def main():
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=OWNER_ID, text="Test notification")
asyncio.run(main())
PY
        ;;
    *)
        echo "Usage: $0 {run [--as-service]|notify}" >&2
        exit 1
        ;;
esac

