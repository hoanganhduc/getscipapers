#!/bin/bash

echo "Installing UFW (Uncomplicated Firewall)..."
sudo pacman -S --noconfirm ufw

echo "Pulling the latest getscipapers Docker image..."
docker pull ghcr.io/hoanganhduc/getscipapers:latest

echo "Starting getscipapers container..."
docker run -d \
    --name getscipapers-container \
    --restart always \
    -v "$HOME/Downloads:/home/getscipaper/Downloads" \
    -v "$HOME/.config/getscipapers:/home/getscipaper/.config/getscipapers" \
    ghcr.io/hoanganhduc/getscipapers:latest

echo "Pulling the latest IPFS Kubo Docker image..."
docker pull ipfs/kubo:latest

echo "Allowing required ports through UFW (4001, 8080, 5001)..."
sudo ufw allow 4001
sudo ufw allow 8080
sudo ufw allow 5001

echo "Setting up IPFS data and staging directories..."
export ipfs_staging="$HOME/.ipfs"
export ipfs_data="$HOME/.ipfs"

echo "Starting IPFS Kubo container..."
docker run -d \
    --name ipfs_host \
    --restart always \
    -v "$ipfs_staging:/export" \
    -v "$ipfs_data:/data/ipfs" \
    -p 4001:4001 \
    -p 4001:4001/udp \
    -p 127.0.0.1:8080:8080 \
    -p 127.0.0.1:5001:5001 \
    ipfs/kubo:latest

echo "All services started successfully."