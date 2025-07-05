#!/bin/bash
set -e

DEST="/usr/local/bin/chromedriver"

# Get full Chrome version
VERSION_STRING=$(google-chrome --version)
CVER=$(echo "$VERSION_STRING" | sed -nre 's/^Google Chrome ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\s*$/\1/p')
if [ -z "$CVER" ]; then
  echo "❌ Failed to parse Chrome version: $VERSION_STRING"
  exit 1
fi

MAJOR=$(echo "$CVER" | cut -d. -f1)
MINOR=$(echo "$CVER" | cut -d. -f2)
BUILD=$(echo "$CVER" | cut -d. -f3)

if [ "$MAJOR" -ge 115 ]; then
  REGEX="^${MAJOR}\\\\.${MINOR}\\\\.${BUILD}\\\\."
  URL=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json \
    | jq -r '.versions[] | select(.version | test("'"$REGEX"'")) | .downloads.chromedriver[] | select(.platform == "linux64") | .url' \
    | tail -1)

  if [ -z "$URL" ]; then
    echo "❌ No matching ChromeDriver URL found"
    exit 1
  fi

  VERSION=$(echo "$URL" | sed -nre 's!.*/([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)/.*!\1!p')
  SRCFILE=chromedriver-linux64/chromedriver
else
  SHORT="${BUILD}"
  VERSION=$(wget -qO- "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${SHORT}")
  URL="https://chromedriver.storage.googleapis.com/${VERSION}/chromedriver_linux64.zip"
  SRCFILE=chromedriver
fi

echo "📦 Installing ChromeDriver version ${VERSION} for Chrome ${CVER}"

TMPDIR=$(mktemp -d)
ZIPFILE="${TMPDIR}/chromedriver.zip"

wget -q -O "$ZIPFILE" "$URL"
unzip -q "$ZIPFILE" -d "$TMPDIR"
mv "${TMPDIR}/${SRCFILE}" "$DEST"
chmod +x "$DEST"
rm -rf "$TMPDIR"

echo "✅ Installed to ${DEST}"
