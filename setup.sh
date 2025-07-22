#!/bin/bash
set -e

IMAGE_NAME="rekku_freedom_project"
NEEDS_SUDO=""
AUTO_YES=false
NO_CACHE=false

# Parse args
for arg in "$@"; do
  case "$arg" in
    --cicd) AUTO_YES=true ;;
    --no-cache) NO_CACHE=true ;;
  esac
done

# Load .env if available
if [ -f .env ]; then
  source .env
else
  echo "⚠️  .env file not found. Some variables may be missing."
fi

# Check Docker install
if ! command -v docker &> /dev/null; then
  echo "❌ Docker is not installed. Install now? [y/N]"
  if [ "$AUTO_YES" = true ]; then answer="y"; else read -r answer; fi
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    echo "🔧 Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "✅ Docker installed."
  else
    echo "⛔ Aborted. Please install Docker manually and re-run."
    exit 1
  fi
fi

# Check Docker permission
if ! docker info > /dev/null 2>&1; then
  echo "⚠️  User $(whoami) lacks Docker permissions. Add to group? [y/N]"
  if [ "$AUTO_YES" = true ]; then addgroup="y"; else read -r addgroup; fi
  if [[ "$addgroup" =~ ^[Yy]$ ]]; then
    HOST_USER=$(whoami)
    sudo usermod -aG docker "$HOST_USER"
    echo "✅ Added to docker group. Re-login recommended."
    NEEDS_SUDO="sudo"
  else
    echo "⏳ Using sudo for Docker commands."
    NEEDS_SUDO="sudo"
  fi
fi

# Build options
BUILD_ARGS="-t $IMAGE_NAME"
if [ "$NO_CACHE" = true ]; then
  BUILD_ARGS="--no-cache $BUILD_ARGS"
fi

# Build Docker image
echo "🐳 Building Docker image: $IMAGE_NAME"
$NEEDS_SUDO docker build $BUILD_ARGS .

echo "✅ Docker image built."

echo ""
echo "🔁 To start with live logs:"
echo "    ./start.sh"
echo ""
echo "🎉 Setup complete!"
