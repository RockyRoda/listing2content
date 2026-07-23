# Build the image and run the Listing2Content container on http://localhost:8000
# with a fresh SQLite DB. OPENROUTER_API_KEY is passed from the repo-root .env.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

docker build -t listing2content $root
docker run -d --name listing2content `
  --env-file "$root\.env" `
  -p 8000:8000 `
  listing2content

Write-Host "Listing2Content running at http://localhost:8000"
