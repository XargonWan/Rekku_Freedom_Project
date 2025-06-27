#!/bin/bash

IMAGE_NAME="rekku_bot"

source .env

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
  echo "⚠️ Esecuzione con sudo (nessun accesso diretto al socket Docker)"
  DOCKER_CMD="sudo docker"
fi

echo "🚀 Avvio del bot Rekku in Docker..."

$DOCKER_CMD run --rm -it \
  -v "$SELENIUM_PROFILE_DIR":/app/selenium_profile \
  -e SELENIUM_PROFILE_DIR="/app/selenium_profile" \
  --env-file .env \
  "$IMAGE_NAME"
