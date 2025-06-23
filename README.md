# Docker Container for Running getscipapers

## Overview

This guide explains how to use the `getscipapers` tool inside a Docker container. The container includes all necessary dependencies, so you can start downloading scientific papers immediately—no manual setup required.

## Quick Start

### 1. Pull and Run the Prebuilt Image

To get started quickly, pull the latest image from GitHub Container Registry and run it:

```bash
docker pull ghcr.io/hoanganhduc/getscipapers:latest
docker run -it --rm -v $(pwd):/workspace ghcr.io/hoanganhduc/getscipapers:latest
```

This mounts your current directory to `/workspace` inside the container, so you can easily access your files.

### 2. Build and Run Locally

If you want to build the image yourself:

```bash
docker build -t getscipapers .
docker run -it --rm -v $(pwd):/workspace getscipapers
```

### 3. Run in Detached Mode with Persistent Storage

To keep the container running in the background and ensure your downloads and configuration persist:

```bash
docker run -d \
    --name getscipapers-container \
    --restart always \
    -v $HOME/Downloads:/home/getscipaper/Downloads \
    -v $HOME/.config/getscipapers:/home/getscipaper/.config/getscipapers \
    ghcr.io/hoanganhduc/getscipapers:latest
```

This setup saves downloaded papers and settings to your host machine.

## Optional: Integrate with IPFS

To use IPFS with getscipapers, run an IPFS Kubo daemon in a separate container:

```bash
docker pull ipfs/kubo:latest
sudo ufw allow 4001
sudo ufw allow 8080
sudo ufw allow 5001

export ipfs_staging=$HOME/.ipfs
export ipfs_data=$HOME/.ipfs

docker run -d \
    --name ipfs_host \
    --restart always \
    -v $ipfs_staging:/export \
    -v $ipfs_data:/data/ipfs \
    -p 4001:4001 \
    -p 4001:4001/udp \
    -p 127.0.0.1:8080:8080 \
    -p 127.0.0.1:5001:5001 \
    ipfs/kubo:latest
```

This starts the IPFS daemon with persistent storage and the required ports.

## Running getscipapers Commands

To run `getscipapers` inside the container, use:

```bash
docker exec -it getscipapers-container getscipapers --help
```

### Optional: Create a Convenience Script

For easier access, create a script at `~/.local/bin/getscipapers`:

```bash
#!/bin/bash
CONTAINER_NAME="getscipapers-container"

if [ $# -lt 1 ]; then
    echo "Usage: $0 [arguments...]"
    exit 1
fi

COMMAND=("getscipapers" "$@")

if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

if ! docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "Error: Container '$CONTAINER_NAME' is not running"
    exit 1
fi

docker exec -i "$CONTAINER_NAME" "${COMMAND[@]}"
```

Make it executable:

```bash
chmod +x ~/.local/bin/getscipapers
```

Now you can run `getscipapers` directly from your terminal:

```bash
getscipapers --help
```

---

For more information, see the official documentation or repository.
