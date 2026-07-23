#!/usr/bin/env bash
# Build the image and run the Listing2Content container on http://localhost:8000
# with a fresh SQLite DB. OPENROUTER_API_KEY is passed from the repo-root .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker build -t listing2content "$ROOT"
docker run -d --name listing2content \
  --env-file "$ROOT/.env" \
  -p 8000:8000 \
  listing2content

echo "Listing2Content running at http://localhost:8000"
