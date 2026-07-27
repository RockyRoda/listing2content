# Phase 4 smoke test: AI content generation on http://localhost:8000
# Assumes the app is already running (Docker or uvicorn) and that
# OPENROUTER_API_KEY reached it - this makes real LLM calls and takes ~30s.
# Run: .\verify-phase4.ps1  [-PhotoDir C:\path\with\jpgs]
param([string]$PhotoDir = "C:\Windows\Web\Wallpaper\ThemeA")

$ErrorActionPreference = "SilentlyContinue"
$base = "http://localhost:8000"
$pass = 0; $fail = 0

function Check($name, $cond) {
  if ($cond) { Write-Host "  PASS  $name" -ForegroundColor Green; $script:pass++ }
  else       { Write-Host "  FAIL  $name" -ForegroundColor Red;   $script:fail++ }
}

# Wait for the server to be up.
$up = $false
for ($i = 0; $i -lt 30; $i++) {
  try { if ((Invoke-RestMethod "$base/health").status -eq "ok") { $up = $true; break } } catch {}
  Start-Sleep -Milliseconds 700
}
Check "health endpoint responds ok" $up
if (-not $up) { Write-Host "Server not reachable at $base - start it first." -ForegroundColor Yellow; return }

$photos = @(Get-ChildItem -Path $PhotoDir -Filter *.jpg | Select-Object -First 2)
if ($photos.Count -lt 2) {
  Write-Host "Need at least 2 .jpg files in $PhotoDir - pass -PhotoDir to point elsewhere." -ForegroundColor Yellow
  return
}

# --- Set up an agent with a voice profile ---
$email = "phase4+$(Get-Random)@studio.com"
$creds = @{ email = $email; password = "secret123" } | ConvertTo-Json
$auth  = Invoke-RestMethod -Method Post -Uri "$base/api/auth/signup" -Body $creds -ContentType "application/json"
$H     = @{ Authorization = "Bearer $($auth.token)" }
& curl.exe -s -X PUT "$base/api/voice-profile" -H "Authorization: Bearer $($auth.token)" `
  -F "tone_notes=Warm, unhurried, a little wry." | Out-Null

function New-Listing($title) {
  $body = @{ title = $title; location = "Wailea, Maui"; price = 8950000; beds = 4; baths = 4.5;
             features = "Infinity pool, outdoor kitchen, private beach path" } | ConvertTo-Json
  return Invoke-RestMethod -Method Post -Uri "$base/api/listings" -Body $body -ContentType "application/json" -Headers $H
}

# --- A listing with no photos is rejected before any LLM call ---
$bare = New-Listing "Bare listing"
$bareCode = 0
try { Invoke-RestMethod -Method Post -Uri "$base/api/listings/$($bare.id)/package" -Headers $H }
catch { $bareCode = $_.Exception.Response.StatusCode.value__ }
Check "generate with no photos -> 400" ($bareCode -eq 400)

# --- Real listing with photos ---
$listing = New-Listing "Oceanfront Villa Kai"
$curlArgs = @("-s", "-X", "POST", "$base/api/listings/$($listing.id)/photos",
              "-H", "Authorization: Bearer $($auth.token)")
foreach ($p in $photos) { $curlArgs += @("-F", "files=@$($p.FullName);type=image/jpeg") }
$withPhotos = (& curl.exe @curlArgs) | ConvertFrom-Json
$photoIds = @($withPhotos.photos | ForEach-Object { $_.id })
Check "uploaded $($photos.Count) photos to the listing" ($photoIds.Count -eq $photos.Count)

# --- No package exists until one is generated ---
$preCode = 0
try { Invoke-RestMethod -Uri "$base/api/listings/$($listing.id)/package" -Headers $H }
catch { $preCode = $_.Exception.Response.StatusCode.value__ }
Check "GET package before generating -> 404" ($preCode -eq 404)

# --- Generate (real vision + assembly calls) ---
Write-Host "  ....  generating (real LLM calls, please wait)" -ForegroundColor DarkGray
$sw  = [Diagnostics.Stopwatch]::StartNew()
$pkg = Invoke-RestMethod -Method Post -Uri "$base/api/listings/$($listing.id)/package" -Headers $H
$sw.Stop()

Check "generate returns a draft package"            ($pkg.status -eq "draft")
Check "generated in under 60s ($([int]$sw.Elapsed.TotalSeconds)s)" ($sw.Elapsed.TotalSeconds -lt 60)
Check "carousel has one slide per photo"            ($pkg.slides.Count -eq $photos.Count)
Check "slides reference the listing's photos in order" (
  (@($pkg.slides | ForEach-Object { $_.listing_photo_id }) -join ",") -eq ($photoIds -join ","))
Check "slides carry a photo_url"                    (-not ($pkg.slides | Where-Object { -not $_.photo_url }))
Check "every slide caption has text"                (-not ($pkg.slides | Where-Object { $_.caption.Length -lt 10 }))
Check "caption set has 3-5 labelled captions"       (($pkg.captions.Count -ge 3) -and ($pkg.captions.Count -le 5))
Check "reel script is substantial"                  ($pkg.reel_script.Length -gt 200)
# Sampled, not guaranteed: the model occasionally writes "from Photo 1" into a
# shot direction. Measured at 0 leaks in 40 runs, so a failure here means the
# behaviour came back, not that the check is broken.
Check "copy does not leak photo numbering"          ($pkg.reel_script -notmatch "(?i)photo\s*\d")

# The photos are only reachable with the bearer token.
$img = Invoke-WebRequest -Uri "$base/api$($pkg.slides[0].photo_url)" -Headers $H -UseBasicParsing
Check "slide photo_url serves the image to its owner" ($img.StatusCode -eq 200)

# --- The package persists ---
$fetched = Invoke-RestMethod -Uri "$base/api/listings/$($listing.id)/package" -Headers $H
Check "GET after generating returns the same package" ($fetched.id -eq $pkg.id)

# --- Regenerating replaces the previous draft ---
Write-Host "  ....  regenerating" -ForegroundColor DarkGray
$again = Invoke-RestMethod -Method Post -Uri "$base/api/listings/$($listing.id)/package" -Headers $H
Check "regenerate produces a new package"           ($again.id -ne $pkg.id)
Check "regenerate leaves only the newest package"   ((Invoke-RestMethod -Uri "$base/api/listings/$($listing.id)/package" -Headers $H).id -eq $again.id)

# --- Another agent cannot see or generate it ---
$other = Invoke-RestMethod -Method Post -Uri "$base/api/auth/signup" -ContentType "application/json" `
  -Body (@{ email = "other+$(Get-Random)@studio.com"; password = "secret123" } | ConvertTo-Json)
$otherH = @{ Authorization = "Bearer $($other.token)" }
$getCode = 0; $postCode = 0
try { Invoke-RestMethod -Uri "$base/api/listings/$($listing.id)/package" -Headers $otherH }
catch { $getCode = $_.Exception.Response.StatusCode.value__ }
try { Invoke-RestMethod -Method Post -Uri "$base/api/listings/$($listing.id)/package" -Headers $otherH }
catch { $postCode = $_.Exception.Response.StatusCode.value__ }
Check "another agent's GET -> 404"  ($getCode -eq 404)
Check "another agent's POST -> 404" ($postCode -eq 404)

$anonCode = 0
try { Invoke-RestMethod -Uri "$base/api/listings/$($listing.id)/package" }
catch { $anonCode = $_.Exception.Response.StatusCode.value__ }
Check "no token -> 401" ($anonCode -eq 401)

# --- Deleting a photo a slide uses clears the reference instead of erroring ---
$usedPhoto = $again.slides[0].listing_photo_id
Invoke-RestMethod -Method Delete -Uri "$base/api/listings/$($listing.id)/photos/$usedPhoto" -Headers $H | Out-Null
$afterDelete = Invoke-RestMethod -Uri "$base/api/listings/$($listing.id)/package" -Headers $H
Check "deleting a used photo clears the slide reference" (
  $null -eq ($afterDelete.slides | Where-Object { $_.listing_photo_id -eq $usedPhoto }))

Write-Host ""
Write-Host "  Package for listing $($listing.id): $base/listings/package/?id=$($listing.id)" -ForegroundColor DarkGray
Write-Host "  Sign in as $email / secret123 to view it." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  $pass passed, $fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
