# Build the image and run the Listing2Content container on http://localhost:8000
# with a fresh SQLite DB. OPENROUTER_API_KEY reaches the container at run time
# via --env-file and is never baked into the image.
#
# ErrorActionPreference is deliberately left alone: docker writes build progress
# to stderr, which PowerShell 5.1 wraps as a NativeCommandError, so "Stop" here
# aborts the script mid-build and never reaches docker run. Exit codes are
# checked explicitly instead.

$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$name = "listing2content"
$url = "http://localhost:8000"

# Readiness is probed over the IPv4 loopback, not "localhost". Windows resolves
# localhost to ::1 first, and Docker Desktop's [::]:8000 publish does not
# actually forward, so an IPv6-first probe stalls until it times out and never
# sees the healthy app. Browsers fall back to IPv4 on their own, so the URL
# shown to the user stays localhost.
$probe = "http://127.0.0.1:8000/health"

if (-not (Test-Path $envFile)) {
  Write-Host "No .env found at $envFile" -ForegroundColor Yellow
  Write-Host "Copy .env.example to .env and add your OPENROUTER_API_KEY, then run this again." -ForegroundColor Yellow
  exit 1
}

docker build -t $name $root
if ($LASTEXITCODE -ne 0) {
  Write-Host "docker build failed - see the output above." -ForegroundColor Red
  exit 1
}

# Replace any previous container. The DB and photos are ephemeral by design
# (docs/PLAN.md decision 13), so there is nothing to preserve.
if (docker ps -aq --filter "name=^$name$") {
  docker rm -f $name | Out-Null
}

docker run -d --name $name --env-file $envFile -p 8000:8000 $name | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "docker run failed - see the output above." -ForegroundColor Red
  exit 1
}

Write-Host "Waiting for $url ..."
for ($i = 0; $i -lt 60; $i++) {
  try {
    if ((Invoke-RestMethod $probe -TimeoutSec 2).status -eq "ok") {
      Write-Host "Listing2Content running at $url" -ForegroundColor Green
      exit 0
    }
  } catch {}
  Start-Sleep -Milliseconds 500
}

Write-Host "Container started but $probe never answered." -ForegroundColor Red
docker ps --filter "name=$name" --format "  {{.Names}}  {{.Status}}  {{.Ports}}"
Write-Host "Last 20 log lines:" -ForegroundColor Yellow
docker logs --tail 20 $name
exit 1
