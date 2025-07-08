#!/usr/bin/env bash
set -e

cd /app
ENV_FILE="/app/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

CMD="${1:-help}"
shift || true

usage() {
    echo "Usage: $0 {run [--as-service]|notify}" >&2
    exit 1
}

case "$CMD" in
    run)
        exec python3 /app/main.py "$@"
        ;;
    notify)
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
        usage
        ;;
esac
