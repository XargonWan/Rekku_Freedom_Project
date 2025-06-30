#!/bin/bash

set -e

IMAGE_NAME="rekku_the_bot"
NEEDS_SUDO=""

source .env

# 🐳 Verifica se Docker è installato
if ! command -v docker &> /dev/null; then
  echo "❌ Docker non è installato."
  echo "Vuoi installarlo ora? (richiede sudo) [y/N]"
  read -r risposta
  if [[ "$risposta" =~ ^[Yy]$ ]]; then
    echo "🔧 Installazione di Docker..."
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "✅ Docker installato con successo."
  else
    echo "⛔ Interrotto. Installa Docker manualmente e riprova."
    exit 1
  fi
fi

# 🔒 Verifica accesso al socket Docker
if ! docker info > /dev/null 2>&1; then
  echo "⚠️ L'utente $(whoami) non ha accesso al daemon Docker."
  echo "Vuoi aggiungerlo al gruppo docker per evitare sudo in futuro? [y/N]"
  read -r addgroup
  if [[ "$addgroup" =~ ^[Yy]$ ]]; then
    sudo usermod -aG docker "$USER"
    echo "✅ Utente aggiunto al gruppo docker."
    echo "🔁 Riavvia la sessione o esegui 'newgrp docker' per applicare subito."
    echo "⏳ Procedo comunque usando sudo per ora..."
    NEEDS_SUDO="sudo"
  else
    echo "⏳ Procedo usando sudo..."
    NEEDS_SUDO="sudo"
  fi
fi

# 🐳 Costruzione immagine Docker
echo "🐳 Costruzione immagine Docker: $IMAGE_NAME"
$NEEDS_SUDO docker build -t "$IMAGE_NAME" .

echo "✅ Immagine Docker aggiornata."

echo ""
echo "📦 Volume persistente consigliato per i cookie Selenium:"
echo "    $NEEDS_SUDO docker run -v $(pwd)/selenium_profile:/app/selenium_profile $IMAGE_NAME"

echo ""
echo "🔁 Per avviare con log live:"
echo "    ./start.sh"

echo ""
echo "🎉 Setup completato!"
