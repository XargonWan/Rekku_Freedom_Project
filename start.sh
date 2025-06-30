#!/bin/bash

IMAGE_NAME="rekku_the_bot"
ENV_FILE=".env"

# Carica variabili da .env solo se esiste
if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
  echo "✅ Variabili d'ambiente caricate da $ENV_FILE"
else
  echo "❌ Errore: file .env mancante."
  exit 1
fi

PORT="${WEBVIEW_PORT:-5005}"

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

# Rimuove eventuale container esistente con lo stesso nome
if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -q '^rekku_container$'; then
  echo "🧹 Container 'rekku_container' già esistente, rimozione in corso..."
  $DOCKER_CMD rm -f rekku_container > /dev/null
fi

echo "🚀 Avvio del bot Rekku in Docker sulla porta $PORT..."

$DOCKER_CMD run --rm -it \
  --name rekku_container \
  --env-file "$ENV_FILE" \
  -v "$(pwd)/logs:/app/debug_logs" \
  -v "$(pwd)/selenium_profile:/app/selenium_profile" \
  -p $PORT:5005 \
  "$IMAGE_NAME"
