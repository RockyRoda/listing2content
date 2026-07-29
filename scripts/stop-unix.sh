#!/usr/bin/env bash
# Stop and remove the Listing2Content container. The DB and photos are
# ephemeral, so stopping discards all data (expected for v1).
#
# Shared implementation: stop-mac.sh and stop-linux.sh both delegate here.
set -euo pipefail

NAME="listing2content"

if [ -n "$(docker ps -aq --filter "name=^${NAME}$")" ]; then
  docker rm -f "$NAME" >/dev/null
  echo "Listing2Content stopped"
else
  echo "Listing2Content was not running"
fi
