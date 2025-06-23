#!/bin/sh
# Ensure IPFS repository is initialized
if [ ! -f "$IPFS_PATH/config" ]; then
    echo "Initializing IPFS repository at $IPFS_PATH..."
    ipfs init || { echo "IPFS init failed"; exit 1; }
fi

# Start IPFS daemon quietly in the background
ipfs daemon > /dev/null 2>&1 &
# Wait briefly to ensure daemon starts
sleep 2

# Check if IPFS daemon is running
if ! ps aux | grep -v grep | grep "ipfs daemon" > /dev/null; then
    echo "Error: IPFS daemon failed to start"
    exit 1
fi