#!/bin/bash

# Start the Docker daemon in the background, suppressing output
sudo dockerd > /dev/null 2>&1 &

# Wait for Docker daemon to become ready (timeout after 60 seconds)
timeout=60
while ! docker info > /dev/null 2>&1; do
  sleep 1
  ((timeout--))
  if [ $timeout -le 0 ]; then
    echo "Docker daemon failed to start."
    exit 1
  fi
done

# Install UFW (Uncomplicated Firewall) using pacman
echo "Installing UFW (Uncomplicated Firewall)..."
sudo pacman -S --noconfirm ufw

# Pull the latest getscipapers Docker image from GitHub Container Registry
echo "Pulling the latest getscipapers Docker image..."
docker pull ghcr.io/hoanganhduc/getscipapers:latest

# Create and bind Docker volumes for persistent storage
# This ensures that data in these directories persists across container restarts
# Docker volume names cannot contain slashes, so we use names with dots or plain names
for volume_name in "Downloads" ".config_getscipapers" ".ipfs"; do
  # Map volume names to source directories in $HOME
  # For example, ".config_getscipapers" maps to "$HOME/.config/getscipapers"
  source="$HOME/${volume_name//_//}"
  mkdir -p "$source"  # Ensure the source directory exists
  docker volume create "$volume_name" \
    --driver "local" \
    --opt "type=none" \
    --opt "device=$source" \
    --opt "o=bind"
done

# Start the getscipapers container with the appropriate volume mounts
echo "Starting getscipapers container..."
docker run -d \
  --name getscipapers-container \
  --restart always \
  -v Downloads:/home/getscipaper/Downloads \
  -v .config/getscipapers:/home/getscipaper/.config/getscipapers \
  ghcr.io/hoanganhduc/getscipapers:latest

# Pull the latest IPFS Kubo Docker image
echo "Pulling the latest IPFS Kubo Docker image..."
docker pull ipfs/kubo:latest

# Allow required ports through the firewall for IPFS and getscipapers
echo "Allowing required ports through UFW (4001, 8080, 5001)..."
sudo ufw allow 4001
sudo ufw allow 8080
sudo ufw allow 5001

# Set up environment variables for IPFS data and staging directories
echo "Setting up IPFS data and staging directories..."
export ipfs_staging="$HOME/.ipfs"
export ipfs_data="$HOME/.ipfs"

# Start the IPFS Kubo container with volume mounts and port mappings
echo "Starting IPFS Kubo container..."
docker run -d \
  --name ipfs_host \
  --restart always \
  -v .ipfs:/data/ipfs \
  -v .ipfs:/export \
  -p 4001:4001 \
  -p 4001:4001/udp \
  -p 127.0.0.1:8080:8080 \
  -p 127.0.0.1:5001:5001 \
  ipfs/kubo:latest

echo "All services started successfully."