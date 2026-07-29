#!/usr/bin/env bash
# Build the image and run the Listing2Content container on http://localhost:8000
# with a fresh SQLite DB. OPENROUTER_API_KEY reaches the container at run time
# via --env-file and is never baked into the image.
#
# Shared implementation: start-mac.sh and start-linux.sh both delegate here,
# since the Docker commands are identical on the two platforms.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
NAME="listing2content"
URL="http://localhost:8000"

# Readiness is probed over the IPv4 loopback rather than "localhost", which can
# resolve to ::1 first while Docker's [::]:8000 publish does not forward. curl
# would fall back on its own, but probing the address the container actually
# publishes on keeps the wait deterministic.
PROBE="http://127.0.0.1:8000/health"

if [ ! -f "$ENV_FILE" ]; then
  echo "No .env found at $ENV_FILE"
  echo "Copy .env.example to .env and add your OPENROUTER_API_KEY, then run this again."
  exit 1
fi

docker build -t "$NAME" "$ROOT"

# Replace any previous container. The DB and photos are ephemeral by design
# (docs/PLAN.md decision 13), so there is nothing to preserve.
if [ -n "$(docker ps -aq --filter "name=^${NAME}$")" ]; then
  docker rm -f "$NAME" >/dev/null
fi

docker run -d --name "$NAME" --env-file "$ENV_FILE" -p 8000:8000 "$NAME" >/dev/null

echo "Waiting for $URL ..."
for ((i = 0; i < 60; i++)); do
  # -s without -S: connection resets are expected while the app is still booting.
  if curl -fs --max-time 2 "$PROBE" | grep -q '"ok"'; then
    echo "Listing2Content running at $URL"
    exit 0
  fi
  sleep 0.5
done

echo "Container started but $PROBE never answered."
docker ps --filter "name=$NAME" --format "  {{.Names}}  {{.Status}}  {{.Ports}}"
echo "Last 20 log lines:"
docker logs --tail 20 "$NAME"
exit 1
