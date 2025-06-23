#!/bin/sh

# Start IPFS daemon quietly in the background
ipfs daemon > /dev/null 2>&1 &
# Wait briefly to ensure daemon starts
sleep 2

# Check if IPFS daemon is running
if ! ps aux | grep -v grep | grep "ipfs daemon" > /dev/null; then
    echo "Error: IPFS daemon failed to start"
    exit 1
fi

# Execute the provided command (e.g., bash or getscipapers)
exec "$@"