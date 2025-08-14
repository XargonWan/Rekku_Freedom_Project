#!/usr/bin/env bash
set -e

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

MODE="${1:-run}"
shift || true

case "$MODE" in
    run)
        if [ "${1:-}" = "--as-service" ]; then
            shift
            log "Running main.py in service mode"
            exec /app/venv/bin/python /app/main.py --service "$@"
        else
            log "Running main.py interactively"
            exec /app/venv/bin/python /app/main.py "$@"
        fi
        ;;
    notify)
        log "Sending test notification"
        /app/venv/bin/python - <<'PY'
import asyncio
from telegram import Bot
from core.config import BOT_TOKEN, TRAINER_ID
async def main():
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=TRAINER_ID, text="Test notification")
asyncio.run(main())
PY
        ;;
    *)
        echo "Usage: $0 {run [--as-service]|notify}" >&2
        exit 1
        ;;
esac

