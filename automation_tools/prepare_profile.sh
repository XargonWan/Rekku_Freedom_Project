#!/bin/bash
set -e

source .env

echo "🧪 Preparazione del profilo Selenium"

VERSION=138.0.7204.49
BASE_URL="https://storage.googleapis.com/chrome-for-testing-public/${VERSION}/linux64"

TMP_DIR=$(mktemp -d)
export CHROME_BIN="$TMP_DIR/chrome-linux64/chrome"
export CHROMEDRIVER_PATH="$TMP_DIR/chromedriver-linux64/chromedriver"
export PATH="$TMP_DIR/chromedriver-linux64:$PATH"

echo "⬇️ Scarico Chrome v$VERSION..."
wget -q "${BASE_URL}/chrome-linux64.zip" -O "$TMP_DIR/chrome.zip"
wget -q "${BASE_URL}/chromedriver-linux64.zip" -O "$TMP_DIR/chromedriver.zip"

echo "📦 Estrazione..."
unzip -qo "$TMP_DIR/chrome.zip" -d "$TMP_DIR"
unzip -qo "$TMP_DIR/chromedriver.zip" -d "$TMP_DIR"

chmod +x "$CHROME_BIN" "$CHROMEDRIVER_PATH"

echo "✅ Chrome pronto: $CHROME_BIN"
echo "✅ ChromeDriver pronto: $CHROMEDRIVER_PATH"
"$CHROME_BIN" --version
"$CHROMEDRIVER_PATH" --version

# 🗂️ Crea directory profilo Selenium se non esiste
mkdir -p "$SELENIUM_PROFILE_DIR"
sudo chown -R "1000:1000" "$SELENIUM_PROFILE_DIR"
chmod u+rw "$SELENIUM_PROFILE_DIR"

echo ""
echo "🌐 Avvio Chrome per login manuale su ChatGPT..."
"$CHROME_BIN" \
    --user-data-dir="$SELENIUM_PROFILE_DIR" \
    --no-sandbox \
    --disable-dev-shm-usage \
    --start-maximized \
    "https://chat.openai.com"

echo ""
read -p "✅ Premi INVIO quando hai completato il login e chiuso il browser..."

# 🗜️ Comprimi profilo
echo "🗜️  Comprimo il profilo Selenium..."
tar czf selenium_profile.tar.gz selenium_profile

echo "✅ Profilo creato: selenium_profile.tar.gz"
