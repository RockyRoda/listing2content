#!/usr/bin/env bash
# Stop and remove the Listing2Content container. The DB is ephemeral, so
# stopping discards all data (expected for v1).
set -euo pipefail

docker rm -f listing2content 2>/dev/null || true
echo "Listing2Content stopped"
