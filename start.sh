#!/bin/bash

IMAGE_NAME="rekku_freedom_project"
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

# Define ports
PORT="${WEBVIEW_PORT:-5001}"
INT_PORT="3000"
HOST_IP=$(hostname -I | awk '{print $1}')
WEBVIEW_HOST_ENV="${WEBVIEW_HOST:-$HOST_IP}"

# Check required token
if [[ -z "$BOTFATHER_TOKEN" ]]; then
  echo "❌ Error: BOTFATHER_TOKEN is not set."
  echo "ℹ️  Usage: BOTFATHER_TOKEN=... ./start.sh"
  exit 1
fi

# Determine Docker command (with or without sudo)
if docker info > /dev/null 2>&1; then
  DOCKER_CMD="docker"
else
  echo "⚠️  Running with sudo (no direct Docker access)"
  DOCKER_CMD="sudo docker"
fi

# Ensure logs directory exists with correct permissions
mkdir -p "$(pwd)/logs"
chown -R 1000:1000 "$(pwd)/logs"

# Clean up existing Rekku-related containers
echo "🧹 Cleaning up existing Rekku containers..."
$DOCKER_CMD ps --format '{{.ID}} {{.Image}} {{.Command}}' | grep -E 'rekku_freedom_project|start-vnc\.sh' | awk '{print $1}' | xargs -r $DOCKER_CMD kill

# Remove container if it exists
if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -q '^rekku_freedom_project$'; then
  echo "🧹 Removing existing container 'rekku_freedom_project'..."
  $DOCKER_CMD rm -f rekku_freedom_project > /dev/null
fi

# Prepare persistent home directory
REKKU_HOME="$(pwd)/rekku_home"
if [ ! -d "$REKKU_HOME" ]; then
  echo "📂 Creating persistent Rekku home directory..."
  mkdir -p "$REKKU_HOME"
  chown -R 1000:1000 "$REKKU_HOME"
  chmod u+rw "$REKKU_HOME"
else
  echo "📂 Using existing Rekku home directory."
fi

# Execute selected mode
case "$MODE" in
  run)
    echo "🚀 Starting Rekku container in bot mode on port $PORT..."
    $DOCKER_CMD run --rm -it \
      --name rekku_freedom_project \
      --hostname luna-workstation \
      --env-file "$ENV_FILE" \
      -v "$(pwd)/logs:/app/debug_logs" \
      -v "$(pwd)/persona:/app/persona" \
      -v "$REKKU_HOME:/home/rekku" \
      -v "$(pwd)/.env:/app/.env:ro" \
      -e WEBVIEW_PORT=$PORT \
      -e WEBVIEW_HOST=$WEBVIEW_HOST_ENV \
      -p $PORT:$INT_PORT \
      "$IMAGE_NAME"
    ;;

  shell)
    echo "🐚 Launching interactive shell into Rekku container..."
    $DOCKER_CMD run --rm -it \
      --name rekku_freedom_project \
      --hostname luna-workstation \
      --env-file "$ENV_FILE" \
      -v "$(pwd)/logs:/app/debug_logs" \
      -v "$(pwd)/persona:/app/persona" \
      -v "$REKKU_HOME:/home/rekku" \
      -v "$(pwd)/.env:/app/.env:ro" \
      -e WEBVIEW_PORT=$PORT \
      -e WEBVIEW_HOST=$WEBVIEW_HOST_ENV \
      -p $PORT:$INT_PORT \
      "$IMAGE_NAME" \
      /bin/bash
    ;;

  test_notify)
    echo "📡 Testing direct notification from the container..."
    $DOCKER_CMD run --rm -it \
      --name rekku_freedom_project \
      --hostname luna-workstation \
      --env-file "$ENV_FILE" \
      -v "$(pwd)/logs:/app/debug_logs" \
      -v "$(pwd)/persona:/app/persona" \
      -v "$REKKU_HOME:/home/rekku" \
      -v "$(pwd)/.env:/app/.env:ro" \
      -e WEBVIEW_PORT=$PORT \
      -e WEBVIEW_HOST=$WEBVIEW_HOST_ENV \
      -p $PORT:$INT_PORT \
      "$IMAGE_NAME" \
      python3 -c 'import asyncio; from telegram import Bot; from core.config import BOT_TOKEN, OWNER_ID; bot = Bot(token=BOT_TOKEN); asyncio.run(bot.send_message(chat_id=OWNER_ID, text="🔔 TEST: direct notification from container"))'
    ;;

  *)
    echo "❌ Unknown mode: $MODE"
    echo "Usage: ./start.sh [run|shell|test_notify]"
    exit 1
    ;;
esac
