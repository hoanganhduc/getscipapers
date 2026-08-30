#!/usr/bin/env bash
# Apply optional Kubo settings to the IPFS container of the Compose stack.
#
# getscipapers only reads the Nexus/STC index, so a few of Kubo's defaults --
# which assume a node that also publishes -- are worth revisiting. None of this
# is required; the stack works without it.

set -euo pipefail

CONTAINER="ipfs_host"
PROFILE="readonly"
STORAGE_MAX="20GB"
ASSUME_YES=0

usage() {
	cat <<'USAGE'
Usage: optimize-ipfs.sh [options]

  -c NAME     container to configure (default: ipfs_host)
  -p PROFILE  readonly | fast | lowpower (default: readonly)
  -s SIZE     datastore cap, e.g. 20GB (default: 20GB)
  -y          do not ask for confirmation
  -h          show this message

Profiles:
  readonly    cap the datastore, collect garbage every 12h, and announce only
              pinned content -- a node that pins nothing then announces nothing
  fast        readonly, plus the accelerated DHT client: lower lookup latency
              for more memory and bandwidth
  lowpower    readonly, plus tighter connection limits for a small machine;
              fewer peers means fewer places to find a block

Garbage collection also needs --enable-gc on the daemon; the cap is only
enforced when it runs. See the Docker Compose Guide for the command override.
USAGE
}

while getopts "c:p:s:yh" opt; do
	case "$opt" in
		c) CONTAINER="$OPTARG" ;;
		p) PROFILE="$OPTARG" ;;
		s) STORAGE_MAX="$OPTARG" ;;
		y) ASSUME_YES=1 ;;
		h) usage; exit 0 ;;
		*) usage >&2; exit 2 ;;
	esac
done

case "$PROFILE" in
	readonly|fast|lowpower) ;;
	*) echo "Unknown profile: $PROFILE" >&2; usage >&2; exit 2 ;;
esac

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
	echo "Container '$CONTAINER' is not running." >&2
	echo "Start it with: docker compose up -d ipfs" >&2
	exit 1
fi

echo "Container: $CONTAINER"
echo "Profile:   $PROFILE"
echo "Datastore: $STORAGE_MAX"

if [ "$ASSUME_YES" -eq 0 ]; then
	read -r -p "Apply and restart the daemon? (y/N) " reply
	case "$reply" in
		[Yy]*) ;;
		*) echo "Cancelled."; exit 0 ;;
	esac
fi

# Numbers and booleans need --json; strings are passed as-is.
cfg() { docker exec "$CONTAINER" ipfs config "$@"; }

cfg Datastore.StorageMax "$STORAGE_MAX"
cfg Datastore.GCPeriod 12h
cfg Reprovider.Strategy pinned
echo "set datastore cap, collection period, and pinned-only announcements"

case "$PROFILE" in
	fast)
		cfg --json Routing.AcceleratedDHTClient true
		echo "enabled the accelerated DHT client"
		;;
	lowpower)
		cfg --json Swarm.ConnMgr.HighWater 40
		cfg --json Swarm.ConnMgr.LowWater 20
		echo "lowered the connection limits"
		;;
esac

docker restart "$CONTAINER" >/dev/null
echo "restarted $CONTAINER"
echo
echo "Current values:"
docker exec "$CONTAINER" ipfs config Datastore.StorageMax
docker exec "$CONTAINER" ipfs config Reprovider.Strategy
