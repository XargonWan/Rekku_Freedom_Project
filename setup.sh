#!/bin/bash

# Setup script per Rekku_the_bot
echo "🔧 Creazione ambiente virtuale..."
python3 -m venv venv

echo "✅ Ambiente virtuale creato."

echo "⚙️ Attivazione dell'ambiente..."
source venv/bin/activate

echo "📦 Installazione dipendenze da requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🎉 Setup completato!"
echo "🚀 Avvia il bot con: start.sh"
