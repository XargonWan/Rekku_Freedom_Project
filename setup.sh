#!/bin/bash

set -e

# CI/CD mode: auto-confirm prompts
AUTO_YES=false
for arg in "$@"; do
  if [[ "$arg" == "--cicd" ]]; then
    AUTO_YES=true
  fi
done

IMAGE_NAME="rekku_freedom_project"
NEEDS_SUDO=""

# Load .env if available
if [ -f .env ]; then
  source .env
else
  echo "⚠️  .env file not found. Some variables may be missing."
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
  echo "❌ Docker is not installed."
  echo "Install it now? (requires sudo) [y/N]"
  if [ "$AUTO_YES" = true ]; then
    answer="y"
    echo "Auto-answered: yes"
  else
    read -r answer
  fi
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    echo "🔧 Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "✅ Docker installed successfully."
  else
    echo "⛔ Aborted. Please install Docker manually and re-run this script."
    exit 1
  fi
fi

# Check Docker access
if ! docker info > /dev/null 2>&1; then
  echo "⚠️  User $(whoami) doesn't have access to the Docker daemon."
  echo "Add user to the docker group to avoid sudo in the future? [y/N]"
  if [ "$AUTO_YES" = true ]; then
    addgroup="y"
    echo "Auto-answered: yes"
  else
    read -r addgroup
  fi
  if [[ "$addgroup" =~ ^[Yy]$ ]]; then
    sudo usermod -aG docker "$USER"
    echo "✅ User added to docker group."
    echo "🔁 Re-login or run 'newgrp docker' to apply immediately."
    echo "⏳ Continuing with sudo for now..."
    NEEDS_SUDO="sudo"
  else
    echo "⏳ Continuing with sudo..."
    NEEDS_SUDO="sudo"
  fi
fi

# Build the Docker image
echo "🐳 Building Docker image: $IMAGE_NAME"
$NEEDS_SUDO docker build -t "$IMAGE_NAME" .

echo "✅ Docker image built."

echo ""
echo "🔁 To start with live logs:"
echo "    ./start.sh"
echo ""
echo "🎉 Setup complete!"
