# Phase 5 smoke test: review / approve / edit pass on http://localhost:8000
# Assumes the app is already running (Docker or uvicorn) and that
# OPENROUTER_API_KEY reached it. One real generation seeds the package (~30s);
# every edit and approval check after that is pure API work.
# Run: .\verify-phase5.ps1  [-PhotoDir C:\path\with\jpgs]
param([string]$PhotoDir = "C:\Windows\Web\Wallpaper\ThemeA")

$ErrorActionPreference = "SilentlyContinue"
$base = "http://localhost:8000"
$pass = 0; $fail = 0

function Check($name, $cond) {
  if ($cond) { Write-Host "  PASS  $name" -ForegroundColor Green; $script:pass++ }
  else       { Write-Host "  FAIL  $name" -ForegroundColor Red;   $script:fail++ }
}

function Write-Total($note) {
  Write-Host ""
  Write-Host "  $pass passed, $fail failed$note" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
}

# Every request goes through here so an unexpected HTTP failure is printed
# rather than silently leaving $null behind for a later check to misread.
function Invoke-Api($method, $path, $body, $headers = $null) {
  if ($null -eq $headers) { $headers = $script:H }
  try {
    return Invoke-RestMethod -Method $method -Uri "$base$path" -Headers $headers `
      -Body $body -ContentType "application/json" -ErrorAction Stop
  } catch {
    Write-Host "        $method $path -> HTTP $($_.Exception.Response.StatusCode.value__)" -ForegroundColor DarkYellow
    return $null
  }
}

# Returns the HTTP status of a request that is expected to fail.
function Get-FailCode($method, $path, $headers, $body) {
  try {
    Invoke-RestMethod -Method $method -Uri "$base$path" -Headers $headers -Body $body `
      -ContentType "application/json" -ErrorAction Stop | Out-Null
    return 200
  } catch { return $_.Exception.Response.StatusCode.value__ }
}

# Compares one field across two row sets. Fails when either side is empty: an
# empty-to-empty match is what let a missing package read as a pass.
function Test-SameField($actual, $expected, $field) {
  $left  = @($actual   | ForEach-Object { $_.$field }) -join ","
  $right = @($expected | ForEach-Object { $_.$field }) -join ","
  return ($left.Length -gt 0) -and ($left -eq $right)
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

# --- An agent with a listing and photos ---
$email = "phase5+$(Get-Random)@studio.com"
$auth  = Invoke-Api "Post" "/api/auth/signup" (@{ email = $email; password = "secret123" } | ConvertTo-Json) @{}
$H     = @{ Authorization = "Bearer $($auth.token)" }

function New-ListingWithPhotos($title) {
  $body = @{ title = $title; location = "Wailea, Maui"; price = 8950000; beds = 4; baths = 4.5;
             features = "Infinity pool, outdoor kitchen, private beach path" } | ConvertTo-Json
  $l = Invoke-Api "Post" "/api/listings" $body
  $curlArgs = @("-s", "-X", "POST", "$base/api/listings/$($l.id)/photos",
                "-H", "Authorization: Bearer $($auth.token)")
  foreach ($p in $photos) { $curlArgs += @("-F", "files=@$($p.FullName);type=image/jpeg") }
  & curl.exe @curlArgs | Out-Null
  return $l
}

# Generation is Phase 4, and it can fail for reasons this test is not about (a
# provider hiccup, a key that never reached the container). Report that plainly
# and stop, rather than letting every later check compare nulls.
function New-Package($listingId, $what) {
  Write-Host "  ....  $what (real LLM calls, please wait)" -ForegroundColor DarkGray
  $p = Invoke-Api "Post" "/api/listings/$listingId/package" $null
  if ($null -eq $p) {
    Write-Host "  STOP  $what failed - that is generation (Phase 4), not the review pass." -ForegroundColor Yellow
    Write-Host "        A 502 means the LLM call itself failed: confirm OPENROUTER_API_KEY" -ForegroundColor Yellow
    Write-Host "        reached the app, check the backend log for the exception, and retry." -ForegroundColor Yellow
  }
  return $p
}

# An edit body echoing the package back with every piece of copy replaced.
function New-EditBody($pkg, $reel) {
  return @{
    reel_script = $reel
    slides   = @($pkg.slides   | ForEach-Object { @{ id = $_.id; caption = "Edited slide $($_.order_index)" } })
    captions = @($pkg.captions | ForEach-Object { @{ id = $_.id; text   = "Edited caption $($_.id)" } })
  } | ConvertTo-Json -Depth 5
}

$listing = New-ListingWithPhotos "Oceanfront Villa Kai"

# --- Nothing to review until a package exists ---
$noPkg = @{ reel_script = "No package to edit."; slides = @(); captions = @() } | ConvertTo-Json
Check "edit before generating -> 404" (
  (Get-FailCode "Put" "/api/listings/$($listing.id)/package" $H $noPkg) -eq 404)
Check "approve before generating -> 404" (
  (Get-FailCode "Post" "/api/listings/$($listing.id)/package/approve" $H $null) -eq 404)

# --- Generate the draft to review ---
$pkg = New-Package $listing.id "generating the draft to review"
if ($null -eq $pkg) { Write-Total " (stopped before the review checks)"; return }
Check "generated package starts as a draft" ($pkg.status -eq "draft")

# --- Edit every piece of copy, save, reload ---
$edited = Invoke-Api "Put" "/api/listings/$($listing.id)/package" (New-EditBody $pkg "An edited Reel script.")
Check "edit returns the saved package" ($edited.reel_script -eq "An edited Reel script.")
Check "slide captions took the edit" (
  ($edited.slides.Count -gt 0) -and
  (@($edited.slides | Where-Object { $_.caption -notlike "Edited slide*" }).Count -eq 0))
Check "caption set took the edit" (
  ($edited.captions.Count -gt 0) -and
  (@($edited.captions | Where-Object { $_.text -notlike "Edited caption*" }).Count -eq 0))

$reloaded = Invoke-Api "Get" "/api/listings/$($listing.id)/package" $null
Check "edits survive a reload"           ($reloaded.reel_script -eq "An edited Reel script.")
Check "editing keeps the same package"   (($null -ne $reloaded.id) -and ($reloaded.id -eq $pkg.id))
Check "caption labels are left alone"    (Test-SameField $reloaded.captions $pkg.captions "label")
Check "slides keep their photo bindings" (Test-SameField $reloaded.slides $pkg.slides "listing_photo_id")

# The model decides the slide count, so assert the indexes run 0..n-1 rather
# than hard-coding one per photo.
$orders = @($reloaded.slides | ForEach-Object { $_.order_index })
Check "slides keep their order (0..$($orders.Count - 1))" (
  ($orders.Count -gt 0) -and (($orders -join ",") -eq ((0..($orders.Count - 1)) -join ",")))

# --- Approve, then confirm an edit sends it back to draft ---
$approved = Invoke-Api "Post" "/api/listings/$($listing.id)/package/approve" $null
Check "approve flips the status" ($approved.status -eq "approved")
Check "approval survives a reload" (
  (Invoke-Api "Get" "/api/listings/$($listing.id)/package" $null).status -eq "approved")

$reEdited = Invoke-Api "Put" "/api/listings/$($listing.id)/package" (New-EditBody $approved "A second pass on the script.")
Check "editing an approved package returns it to draft" ($reEdited.status -eq "draft")

# --- Regenerating an approved package hands back a fresh draft ---
Invoke-Api "Post" "/api/listings/$($listing.id)/package/approve" $null | Out-Null
$regen = New-Package $listing.id "regenerating over the approved package"
if ($null -eq $regen) { Write-Total " (stopped before the regeneration checks)"; return }
Check "regenerate replaces approved copy with a draft" ($regen.status -eq "draft")
Check "regenerate produces a new package" (($null -ne $regen.id) -and ($regen.id -ne $pkg.id))

# --- An id from another package is not writable through this one ---
$second = New-ListingWithPhotos "Second listing"
$other  = New-Package $second.id "generating a second package for the cross-package check"
if ($null -eq $other) { Write-Total " (stopped before the cross-package checks)"; return }

$crossBody = (New-EditBody $regen "Should not be saved." | ConvertFrom-Json)
$crossBody.slides[0].id = $other.slides[0].id
Check "editing another package's slide -> 404" (
  (Get-FailCode "Put" "/api/listings/$($listing.id)/package" $H ($crossBody | ConvertTo-Json -Depth 5)) -eq 404)
Check "the rejected edit changed nothing" (
  (Invoke-Api "Get" "/api/listings/$($listing.id)/package" $null).reel_script -eq $regen.reel_script)
Check "the other package is untouched too" (
  (Invoke-Api "Get" "/api/listings/$($second.id)/package" $null).slides[0].caption -eq $other.slides[0].caption)

# --- Owner scoping ---
$intruder = Invoke-Api "Post" "/api/auth/signup" (
  @{ email = "intruder+$(Get-Random)@studio.com"; password = "secret123" } | ConvertTo-Json) @{}
$iH = @{ Authorization = "Bearer $($intruder.token)" }
$body = New-EditBody $regen "Not yours."
Check "another agent's edit -> 404"    ((Get-FailCode "Put"  "/api/listings/$($listing.id)/package" $iH $body) -eq 404)
Check "another agent's approve -> 404" ((Get-FailCode "Post" "/api/listings/$($listing.id)/package/approve" $iH $null) -eq 404)
Check "edit with no token -> 401"      ((Get-FailCode "Put"  "/api/listings/$($listing.id)/package" @{} $body) -eq 401)
Check "approve with no token -> 401"   ((Get-FailCode "Post" "/api/listings/$($listing.id)/package/approve" @{} $null) -eq 401)

Write-Host ""
Write-Host "  Review the package in the UI: $base/listings/package/?id=$($listing.id)" -ForegroundColor DarkGray
Write-Host "  Sign in as $email / secret123, edit a caption, save, then reload." -ForegroundColor DarkGray
Write-Total ""
