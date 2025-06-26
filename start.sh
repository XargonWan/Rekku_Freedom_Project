#!/bin/bash

IMAGE_NAME="rekku_bot"
PROFILE_DIR="$(pwd)/selenium_profile"

mkdir -p "$PROFILE_DIR"

echo "\U0001f680 Avvio del bot Rekku in Docker..."

docker run --rm -it \
  -v "$PROFILE_DIR":/app/selenium_profile \
  "$IMAGE_NAME"
