#!/bin/bash

IMAGE_NAME="rekku_freedom_project"
ENV_FILE=".env"
MODE="${1:-run}"  # Default: run

# Carica variabili da .env solo se esiste
if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
  echo "✅ Variabili d'ambiente caricate da $ENV_FILE"
else
  echo "❌ Errore: file .env mancante."
  exit 1
fi

PORT="${WEBVIEW_PORT:-3001}"
INT_PORT="3001"
# Determina l'host su cui esporre la GUI VNC
HOST_IP=$(hostname -I | awk '{print $1}')
WEBVIEW_HOST_ENV="${WEBVIEW_HOST:-$HOST_IP}"

# Controllo variabile BOTFATHER_TOKEN
if [[ -z "$BOTFATHER_TOKEN" ]]; then
  echo "❌ Errore: la variabile d'ambiente BOTFATHER_TOKEN non è impostata."
  echo "ℹ️  Usa: BOTFATHER_TOKEN=... ./start.sh"
  exit 1
fi

# Verifica se l'utente può usare docker senza sudo
if docker info > /dev/null 2>&1; then
  DOCKER_CMD="docker"
else
  echo "⚠️  Esecuzione con sudo (nessun accesso diretto al socket Docker)"
  DOCKER_CMD="sudo docker"
fi

# Crea la cartella logs se non esiste
mkdir -p "$(pwd)/logs"
chown -R 1000:1000 "$(pwd)/logs"

# Ensure additional volumes exist and are writable
mkdir -p "$(pwd)/selenium_profile" "$(pwd)/persona"
chown -R 1000:1000 "$(pwd)/selenium_profile" "$(pwd)/persona"

# 🧹 Pulisce container avviati con /start-vnc.sh o immagine rekku_freedom_project
echo "🧹 Pulizia container Docker esistenti relativi a Rekku..."
$DOCKER_CMD ps --format '{{.ID}} {{.Image}} {{.Command}}' | grep -E 'rekku_freedom_project|start-vnc\.sh' | awk '{print $1}' | xargs -r $DOCKER_CMD kill

# Rimuove eventuale container esistente con lo stesso nome
if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -q '^rekku_freedom_project$'; then
  echo "🧹 Container 'rekku_freedom_project' già esistente, rimozione in corso..."
  $DOCKER_CMD rm -f rekku_freedom_project > /dev/null
fi

if [ ! -d "$(pwd)/rekku_home" ]; then
  echo "📂 Creazione della cartella 'rekku_home' per i dati persistenti..."
  mkdir -p "$(pwd)/rekku_home"
  chown -R 1000:1000 "$(pwd)/rekku_home"
  chmod u+rw "$(pwd)/rekku_home"
else
  echo "📂 Cartella 'rekku_home' già esistente, verrà utilizzata." 
fi

case "$MODE" in
  run)
    echo "🚀 Avvio del bot Rekku in Docker sulla porta $PORT..."
    $DOCKER_CMD run --rm -it \
      --name rekku_freedom_project \
      --hostname luna-workstation \
      --env-file "$ENV_FILE" \
      -v "$(pwd)/logs:/app/debug_logs" \
      -v "$(pwd)/selenium_profile:/app/selenium_profile" \
      -v "$(pwd)/persona:/app/persona" \
      -v "$(pwd)/rekku_home:/home/rekku" \
      -e WEBVIEW_PORT=$PORT \
      -e WEBVIEW_HOST=$WEBVIEW_HOST_ENV \
      -p $PORT:$INT_PORT \
      "$IMAGE_NAME"
    ;;

  shell)
    echo "🐚 Accesso interattivo al container Rekku..."
    $DOCKER_CMD run --rm -it \
      --name rekku_freedom_project \
      --hostname luna-workstation \
      --env-file "$ENV_FILE" \
      -v "$(pwd)/logs:/app/debug_logs" \
      -v "$(pwd)/selenium_profile:/app/selenium_profile" \
      -v "$(pwd)/persona:/app/persona" \
      -v "$(pwd)/rekku_home:/home/rekku" \
      -e WEBVIEW_PORT=$PORT \
      -e WEBVIEW_HOST=$WEBVIEW_HOST_ENV \
      -p $PORT:$INT_PORT \
      "$IMAGE_NAME" \
      /bin/bash
    ;;

  test_notify)
    echo "📡 Test notifica diretta dal container..."
    $DOCKER_CMD run --rm -it \
      --name rekku_freedom_project \
      --hostname luna-workstation \
      --env-file "$ENV_FILE" \
      -v "$(pwd)/logs:/app/debug_logs" \
      -v "$(pwd)/selenium_profile:/app/selenium_profile" \
      -v "$(pwd)/persona:/app/persona" \
      -v "$(pwd)/rekku_home:/home/rekku" \
      -e WEBVIEW_PORT=$PORT \
      -e WEBVIEW_HOST=$WEBVIEW_HOST_ENV \
      -p $PORT:$INT_PORT \
      "$IMAGE_NAME" \
      python3 -c 'import asyncio; from telegram import Bot; from core.config import BOT_TOKEN, OWNER_ID; bot = Bot(token=BOT_TOKEN); asyncio.run(bot.send_message(chat_id=OWNER_ID, text="🔔 TEST: notifica diretta dal container"))'
    ;;

  *)
    echo "❌ Modalità sconosciuta: $MODE"
    echo "Usa: ./start.sh [run|shell|test_notify]"
    exit 1
    ;;
esac
