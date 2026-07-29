# Phase 7 smoke test: Docker packaging and the start/stop scripts.
# Unlike verify-phase4/5 this one DRIVES the scripts, so it builds the image and
# replaces any running container. Data is ephemeral by design, so nothing is
# lost, but expect it to take a few minutes and to make one real LLM call.
# Run: .\verify-phase7.ps1  [-PhotoDir C:\path\with\jpgs]
param([string]$PhotoDir = "C:\Windows\Web\Wallpaper\ThemeA")

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$name = "listing2content"
$shownUrl = "http://localhost:8000"
$pass = 0; $fail = 0

# Requests go to the IPv4 loopback, not "localhost": Windows resolves localhost
# to ::1 first and Docker Desktop's [::]:8000 publish does not forward, so an
# IPv6-first probe stalls on every attempt.
$base = "http://127.0.0.1:8000"

function Check($name, $cond) {
  if ($cond) { Write-Host "  PASS  $name" -ForegroundColor Green; $script:pass++ }
  else       { Write-Host "  FAIL  $name" -ForegroundColor Red;   $script:fail++ }
}

function Write-Total($note) {
  Write-Host ""
  Write-Host "  $pass passed, $fail failed$note" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
}

# Runs one of the scripts in a child powershell and returns its output and exit
# code. A child process is required because the scripts talk to the user with
# Write-Host, which writes to the host rather than the pipeline - calling them
# with & (...) | Out-String captures nothing at all.
function Invoke-Script($file, $scriptRoot = $PSScriptRoot) {
  $out = & powershell -NoProfile -File (Join-Path $scriptRoot $file) 2>&1 | Out-String
  return [pscustomobject]@{ Out = $out; Code = $LASTEXITCODE }
}

# --- Repo hygiene: the key template ships, the key itself never does ---
Check ".env.example is committed" (
  [bool](& git -C $root ls-files --error-unmatch ".env.example" 2>$null))
Check ".env.example names OPENROUTER_API_KEY" (
  (Get-Content (Join-Path $root ".env.example") -Raw) -match "OPENROUTER_API_KEY")
Check ".env itself is NOT committed" (
  -not [bool](& git -C $root ls-files --error-unmatch ".env" 2>$null))
Check ".dockerignore excludes .env" (
  (Get-Content (Join-Path $root ".dockerignore")) -contains ".env")

# --- The guard for a clean checkout with no .env ---
# Runs the real script from a throwaway root so the repo's own .env is never
# touched: the script derives its root from its own location.
$fakeRoot = Join-Path $env:TEMP "l2c-noenv-$(Get-Random)"
New-Item -ItemType Directory -Path (Join-Path $fakeRoot "scripts") -Force | Out-Null
Copy-Item (Join-Path $PSScriptRoot "start-windows.ps1") (Join-Path $fakeRoot "scripts")
$guard = Invoke-Script "start-windows.ps1" (Join-Path $fakeRoot "scripts")
Check "missing .env stops the script with guidance" (
  ($guard.Code -eq 1) -and ($guard.Out -match "Copy \.env\.example to \.env"))
Check "missing .env never reaches docker build" ($guard.Out -notmatch "transferring dockerfile")
Remove-Item $fakeRoot -Recurse -Force

if (-not (Test-Path (Join-Path $root ".env"))) {
  Write-Host "  SKIP  container checks - this checkout has no .env" -ForegroundColor Yellow
  Write-Total " (repo checks only)"
  return
}

# --- start script brings the app up from nothing ---
Invoke-Script "stop-windows.ps1" | Out-Null
Write-Host "  ....  running start-windows.ps1 (builds the image, please wait)" -ForegroundColor DarkGray
$start = Invoke-Script "start-windows.ps1"
Check "start-windows.ps1 exits 0"                   ($start.Code -eq 0)
Check "start-windows.ps1 reports the URL"           ($start.Out -match [regex]::Escape($shownUrl))
Check "start waited for readiness, not just launch" ($start.Out -match "Waiting for")
Check "health endpoint answers ok"                  ((Invoke-RestMethod "$base/health").status -eq "ok")
Check "port 8000 is published to the host" (
  (& docker ps --filter "name=$name" --format "{{.Ports}}") -match "0.0.0.0:8000->8000")

# --- The image is self-contained and carries no secret ---
Check "no .env inside the image" (
  (& docker run --rm --entrypoint sh $name -c "test -f /app/.env && echo yes || echo no").Trim() -eq "no")
# `docker inspect` would resolve the running CONTAINER (same name as the image),
# whose env correctly does hold the key - the image must be named explicitly.
Check "no OPENROUTER_API_KEY baked into the image" (
  (& docker image inspect $name --format '{{json .Config.Env}}') -notmatch "OPENROUTER_API_KEY")
Check "the key DID reach the running container" (
  [bool](& docker exec $name printenv OPENROUTER_API_KEY))

# --- The built frontend is served by the backend, from the image ---
Check "frontend index is served"        ((Invoke-WebRequest $base -UseBasicParsing).StatusCode -eq 200)
Check "a deep frontend route is served" (
  (Invoke-WebRequest "$base/listings/package/?id=1" -UseBasicParsing).StatusCode -eq 200)

# --- HEALTHCHECK reports healthy (start-period is 20s) ---
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
  if ((& docker inspect $name --format '{{.State.Health.Status}}') -eq "healthy") { $healthy = $true; break }
  Start-Sleep -Milliseconds 1000
}
Check "container HEALTHCHECK reports healthy" $healthy

# --- Fresh DB, and a real generation proving the key works end to end ---
$email = "phase7+$(Get-Random)@studio.com"
$auth = Invoke-RestMethod -Method Post -Uri "$base/api/auth/signup" -ContentType "application/json" `
  -Body (@{ email = $email; password = "secret123" } | ConvertTo-Json)
$H = @{ Authorization = "Bearer $($auth.token)" }
# Compared as raw JSON: Invoke-RestMethod turns [] into $null, and @($null).Count
# is 1, so an "empty" check on the parsed result would never fail.
Check "a new agent starts with no listings" (
  (Invoke-WebRequest "$base/api/listings" -Headers $H -UseBasicParsing).Content.Trim() -eq "[]")

$photos = @(Get-ChildItem -Path $PhotoDir -Filter *.jpg | Select-Object -First 2)
if ($photos.Count -lt 2) {
  Write-Host "  SKIP  generation check - need 2 .jpg files in $PhotoDir" -ForegroundColor Yellow
} else {
  $body = @{ title = "Container villa"; location = "Wailea, Maui"; price = 8950000 } | ConvertTo-Json
  $listing = Invoke-RestMethod -Method Post -Uri "$base/api/listings" -Body $body `
    -ContentType "application/json" -Headers $H
  $curlArgs = @("-s", "-X", "POST", "$base/api/listings/$($listing.id)/photos",
                "-H", "Authorization: Bearer $($auth.token)")
  foreach ($p in $photos) { $curlArgs += @("-F", "files=@$($p.FullName);type=image/jpeg") }
  & curl.exe @curlArgs | Out-Null

  Write-Host "  ....  generating in the container (real LLM calls, please wait)" -ForegroundColor DarkGray
  $pkg = $null
  try {
    $pkg = Invoke-RestMethod -Method Post -Uri "$base/api/listings/$($listing.id)/package" `
      -Headers $H -ErrorAction Stop
  } catch {
    Write-Host "        POST package -> HTTP $($_.Exception.Response.StatusCode.value__)" -ForegroundColor DarkYellow
  }
  Check "generation succeeds in the container (the key works)" ($pkg.status -eq "draft")
  Check "the package has slides and a script" (
    ($pkg.slides.Count -gt 0) -and ($pkg.reel_script.Length -gt 100))
}

# --- start is idempotent: running it again replaces the container ---
$oldId = (& docker inspect $name --format '{{.Id}}')
Write-Host "  ....  running start-windows.ps1 again over the running container" -ForegroundColor DarkGray
$again = Invoke-Script "start-windows.ps1"
Check "second start exits 0 (no name conflict)" ($again.Code -eq 0)
Check "second start replaced the container"     ((& docker inspect $name --format '{{.Id}}') -ne $oldId)
Check "app is reachable after the restart"      ((Invoke-RestMethod "$base/health").status -eq "ok")

# --- Restart wipes the data, as decision 13 intends ---
$goneCode = 0
try { Invoke-RestMethod -Uri "$base/api/listings" -Headers $H -ErrorAction Stop }
catch { $goneCode = $_.Exception.Response.StatusCode.value__ }
Check "the previous session died with the container (401)" ($goneCode -eq 401)

# --- stop removes it, and says so honestly the second time ---
$stop = Invoke-Script "stop-windows.ps1"
Check "stop-windows.ps1 reports it stopped"    ($stop.Out -match "stopped")
Check "container is gone after stop"           (-not [bool](& docker ps -aq --filter "name=^$name$"))
Check "stopping again says it was not running" ((Invoke-Script "stop-windows.ps1").Out -match "was not running")

Write-Host ""
Write-Host "  The app is stopped. Bring it back with .\scripts\start-windows.ps1" -ForegroundColor DarkGray
Write-Total ""
