#!/bin/bash

# --- Docker SD Card Setup Script (Steam Deck) ---
# Moves Docker storage to: /run/media/deck/SD512/docker-data

if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run as root (use sudo ./setup_docker_sd.sh)"
  exit 1
fi

STORAGE_PATH="/run/media/deck/SD512/docker-data"

echo "🛑 Stopping Docker..."
systemctl stop docker
systemctl stop docker.socket

echo "📁 Creating storage directory on SD Card..."
mkdir -p "$STORAGE_PATH"

echo "📝 Configuring /etc/docker/daemon.json..."
if [ ! -d "/etc/docker" ]; then
    mkdir -p /etc/docker
fi

# Create or update daemon.json
cat > /etc/docker/daemon.json <<EOF
{
  "data-root": "$STORAGE_PATH"
}
EOF

echo "🚀 Restarting Docker..."
systemctl start docker

echo "✅ DONE! Docker is now using your SD card for storage."
echo "You can verify this by running: docker info | grep 'Docker Root Dir'"
