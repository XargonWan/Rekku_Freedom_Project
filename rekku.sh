#!/bin/bash
set -e

ENV_FILE=".env"
MODE="${1:-run}"  # Default mode is "run"

# Check if docker compose is available
if ! command -v docker &>/dev/null || ! docker compose version &>/dev/null; then
  echo "❌ 'docker compose' (v2) is required but not found."
  echo "💡 Please install Docker Compose v2: https://docs.docker.com/compose/install/linux/"
  exit 1
fi

# Load environment variables
if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
  echo "✅ Environment variables loaded from $ENV_FILE"
else
  echo "❌ Error: .env file is missing."
  exit 1
fi

SERVICE_NAME="rekku_freedom_project"

case "$MODE" in
  run)
    echo "🚀 Starting Rekku container via Docker Compose..."

    # Prevent conflict with stale container name
    EXISTING=$(docker ps -aqf "name=^$SERVICE_NAME$")
    if [ -n "$EXISTING" ]; then
      echo "🧹 Removing stale container named '$SERVICE_NAME'..."
      docker rm -f "$SERVICE_NAME" || true
    fi

    docker compose up --build
    ;;

  shell)
    echo "🐚 Entering interactive shell into $SERVICE_NAME..."
    docker compose exec "$SERVICE_NAME" /bin/bash
    ;;

  test_notify)
    echo "📡 Testing notification from inside container..."
    docker compose exec "$SERVICE_NAME" python3 -c '
import asyncio
from telegram import Bot
from core.config import BOT_TOKEN, OWNER_ID
bot = Bot(token=BOT_TOKEN)
asyncio.run(bot.send_message(chat_id=OWNER_ID, text="🔔 TEST: direct notification from container"))
'
    ;;

  stop)
    echo "🛑 Stopping and cleaning up containers..."
    docker compose down
    ;;

  *)
    echo "❌ Unknown mode: $MODE"
    echo "Usage: ./rekku.sh [run|shell|test_notify|stop]"
    exit 1
    ;;
esac
