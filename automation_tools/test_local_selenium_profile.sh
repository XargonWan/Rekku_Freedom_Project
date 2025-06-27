#!/bin/bash
set -e

echo "🧪 Test locale del profilo Selenium (estratto da tar.gz)"
ARCHIVE="selenium_profile.tar.gz"
VERSION=138.0.7204.49
BASE_URL="https://storage.googleapis.com/chrome-for-testing-public/${VERSION}/linux64"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "❌ Archivio non trovato: $ARCHIVE"
  exit 1
fi

TMP_DIR=$(mktemp -d)
TMP_PROFILE="$TMP_DIR/selenium_profile"
CHROME_DIR="$TMP_DIR/chrome-linux64"
CHROMEDRIVER_DIR="$TMP_DIR/chromedriver-linux64"

echo "⬇️ Scarico Chrome $VERSION..."
wget -q "${BASE_URL}/chrome-linux64.zip" -O "$TMP_DIR/chrome.zip"
wget -q "${BASE_URL}/chromedriver-linux64.zip" -O "$TMP_DIR/driver.zip"

echo "📦 Estrazione binari..."
unzip -qo "$TMP_DIR/chrome.zip" -d "$TMP_DIR"
unzip -qo "$TMP_DIR/driver.zip" -d "$TMP_DIR"
chmod +x "$CHROME_DIR/chrome" "$CHROMEDRIVER_DIR/chromedriver"

export CHROME_BIN="$CHROME_DIR/chrome"
export CHROMEDRIVER_PATH="$CHROMEDRIVER_DIR/chromedriver"

echo "🔍 Versioni:"
"$CHROME_BIN" --version
"$CHROMEDRIVER_PATH" --version

echo "📂 Estrazione archivio profilo..."
mkdir -p "$TMP_PROFILE"
tar -xzf "$ARCHIVE" -C "$TMP_PROFILE"

echo "🧹 Pulizia file di lock..."
find "$TMP_PROFILE" -type f \( -name "lock" -o -name "Singleton*" \) -exec rm -v {} \;

echo ""
echo "🚀 Avvio Chrome con profilo estratto..."
"$CHROME_BIN" \
    --user-data-dir="$TMP_PROFILE" \
    --no-sandbox \
    --disable-dev-shm-usage \
    --window-size=1280,1024 \
    --no-first-run \
    --no-default-browser-check \
    --enable-logging=stderr \
    --v=1 \
    https://chat.openai.com

echo ""
echo "✅ Test completato. Chrome si è chiuso correttamente."
