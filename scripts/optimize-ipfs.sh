#!/bin/bash
# IPFS Optimization Script for getscipapers
# Optional optimizations for users with more resources

set -e

CONTAINER_NAME="${1:-ipfs_host}"

echo "IPFS Optimization Script"
echo "======================="
echo "This script applies optional optimizations for users with more resources."
echo "The default configuration is already optimized for most users."
echo ""
read -p "Continue with optimizations? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Optimization cancelled."
    exit 0
fi

echo "Target container: $CONTAINER_NAME"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Error: Container '$CONTAINER_NAME' is not running"
    echo "Start it first with: docker-compose up -d ipfs"
    exit 1
fi

echo ""
echo "Select optimization level:"
echo "1. Light (recommended for most users)"
echo "2. Medium (for better performance)"
echo "3. Advanced (for dedicated nodes)"
echo ""
read -p "Enter choice (1-3): " OPT_LEVEL

echo ""
echo "Applying optimizations..."

case $OPT_LEVEL in
    1)
        # Light optimizations
        docker exec "$CONTAINER_NAME" ipfs config Datastore.StorageMax '"50GB"'
        docker exec "$CONTAINER_NAME" ipfs config Datastore.StorageGCWatermark 95
        echo "✓ Increased storage to 50GB"
        ;;
    2)
        # Medium optimizations
        docker exec "$CONTAINER_NAME" ipfs config Datastore.StorageMax '"100GB"'
        docker exec "$CONTAINER_NAME" ipfs config Datastore.StorageGCWatermark 95
        docker exec "$CONTAINER_NAME" ipfs config Swarm.ConnMgr.HighWater 200
        docker exec "$CONTAINER_NAME" ipfs config Swarm.ConnMgr.LowWater 50
        echo "✓ Increased storage to 100GB"
        echo "✓ Optimized connection limits"
        ;;
    3)
        # Advanced optimizations
        docker exec "$CONTAINER_NAME" ipfs config Datastore.StorageMax '"200GB"'
        docker exec "$CONTAINER_NAME" ipfs config Datastore.StorageGCWatermark 98
        docker exec "$CONTAINER_NAME" ipfs config Swarm.ConnMgr.HighWater 300
        docker exec "$CONTAINER_NAME" ipfs config Swarm.ConnMgr.LowWater 100
        docker exec "$CONTAINER_NAME" ipfs config Reprovider.Interval '"12h"'
        echo "✓ Increased storage to 200GB"
        echo "✓ Optimized connection limits"
        echo "✓ Reduced reprovider interval"
        ;;
    *)
        echo "Invalid choice. Using light optimizations."
        docker exec "$CONTAINER_NAME" ipfs config Datastore.StorageMax '"50GB"'
        docker exec "$CONTAINER_NAME" ipfs config Datastore.StorageGCWatermark 95
        ;;
esac

# Restart IPFS daemon to apply changes
echo "Restarting IPFS daemon..."
docker restart "$CONTAINER_NAME"

echo ""
echo "Optimization complete!"
echo "The IPFS node will restart with new settings."
echo ""
echo "Note: These settings help with:"
echo "- Caching more papers locally"
echo "- Better performance for frequent users"
echo "- Contributing to network data availability"

echo ""
echo "To check current settings:"
echo "  docker exec $CONTAINER_NAME ipfs config Datastore.StorageMax"
echo "  docker exec $CONTAINER_NAME ipfs config show | grep -A2 '"Datastore"'""