#!/bin/bash
set -e

ENV_FILE=".env"
MODE="${1:-run}"  # Default mode is "run"

# Load environment variables
if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
  echo "✅ Environment variables loaded from $ENV_FILE"
else
  echo "❌ Error: .env file is missing."
  exit 1
fi

# Detect docker compose command
if command -v docker-compose &>/dev/null; then
  COMPOSE_CMD="docker-compose"
elif command -v docker compose &>/dev/null; then
  COMPOSE_CMD="docker compose"
else
  echo "❌ Neither 'docker compose' nor 'docker-compose' found."
  echo "💡 Do you want to install Docker Compose V2 now? [Y/n]"
  read -r confirm
  if [[ "$confirm" =~ ^[Nn]$ ]]; then
    echo "⛔ Aborted."
    exit 1
  fi

  echo "🔧 Installing Docker Compose V2..."
  sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  echo "✅ Docker Compose installed."
  COMPOSE_CMD="docker compose"
fi

SERVICE_NAME="rekku_freedom_project"

case "$MODE" in
  run)
    echo "🚀 Starting Rekku container via Docker Compose..."
    $COMPOSE_CMD up --build
    ;;

  shell)
    echo "🐚 Entering interactive shell into $SERVICE_NAME..."
    $COMPOSE_CMD exec "$SERVICE_NAME" /bin/bash
    ;;

  test_notify)
    echo "📡 Testing notification from inside container..."
    $COMPOSE_CMD exec "$SERVICE_NAME" python3 -c '
import asyncio
from telegram import Bot
from core.config import BOT_TOKEN, OWNER_ID
bot = Bot(token=BOT_TOKEN)
asyncio.run(bot.send_message(chat_id=OWNER_ID, text="🔔 TEST: direct notification from container"))
'
    ;;

  stop)
    echo "🛑 Stopping and cleaning up containers..."
    $COMPOSE_CMD down
    ;;

  *)
    echo "❌ Unknown mode: $MODE"
    echo "Usage: ./start.sh [run|shell|test_notify|stop]"
    exit 1
    ;;
esac
