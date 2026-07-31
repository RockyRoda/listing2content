# Phase 6 smoke test: the AI chat on http://localhost:8000
# Assumes the app is already running (Docker or uvicorn) and that
# OPENROUTER_API_KEY reached it. Every chat turn is a real LLM call, so this
# talks to the model roughly a dozen times plus one generation (~60s total).
#
# The model decides what to do with each message, so the assertions are about
# what it was clearly asked for (a field it was given, a caption it was told to
# rewrite), never about exact wording.
# Run: .\verify-phase6.ps1  [-PhotoDir C:\path\with\jpgs]
param([string]$PhotoDir = "C:\Windows\Web\Wallpaper\ThemeA")

$ErrorActionPreference = "SilentlyContinue"
# IPv4 loopback, not "localhost": Windows resolves localhost to ::1 first and
# Docker Desktop's [::]:8000 publish does not forward, so an IPv6-first request
# stalls until it times out.
$base = "http://127.0.0.1:8000"
$pass = 0; $fail = 0

function Check($name, $cond) {
  if ($cond) { Write-Host "  PASS  $name" -ForegroundColor Green; $script:pass++ }
  else       { Write-Host "  FAIL  $name" -ForegroundColor Red;   $script:fail++ }
}

function Write-Total($note) {
  Write-Host ""
  Write-Host "  $pass passed, $fail failed$note" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
}

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

function Get-FailCode($method, $path, $headers, $body) {
  try {
    Invoke-RestMethod -Method $method -Uri "$base$path" -Headers $headers -Body $body `
      -ContentType "application/json" -ErrorAction Stop | Out-Null
    return 200
  } catch { return $_.Exception.Response.StatusCode.value__ }
}

# One chat turn. Prints the exchange so a failure can be read rather than guessed at.
function Send-Chat($listingId, $message) {
  Write-Host "    >  $message" -ForegroundColor DarkGray
  $body = @{ message = $message } | ConvertTo-Json
  $r = Invoke-Api "Post" "/api/listings/$listingId/chat" $body
  if ($null -ne $r) {
    Write-Host "    <  $($r.messages[-1].content)" -ForegroundColor DarkGray
  }
  return $r
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

# --- An agent with a bare listing: title only, so chat has fields to fill ---
$email = "phase6+$(Get-Random)@studio.com"
$auth  = Invoke-Api "Post" "/api/auth/signup" (@{ email = $email; password = "secret123" } | ConvertTo-Json) @{}
$H     = @{ Authorization = "Bearer $($auth.token)" }

$listing = Invoke-Api "Post" "/api/listings" (@{ title = "Oceanfront Villa Kai" } | ConvertTo-Json)
$curlArgs = @("-s", "-X", "POST", "$base/api/listings/$($listing.id)/photos",
              "-H", "Authorization: Bearer $($auth.token)")
foreach ($p in $photos) { $curlArgs += @("-F", "files=@$($p.FullName);type=image/jpeg") }
& curl.exe @curlArgs | Out-Null

# Assign before counting. Invoke-RestMethod hands a JSON array back as one
# object rather than enumerating it, so @(Invoke-Api ...).Count is 1 for any
# array - 0 rows or 600 - while @($var).Count unrolls it and counts properly.
$transcript = Invoke-Api "Get" "/api/listings/$($listing.id)/chat" $null
Check "a new listing starts with an empty transcript" (@($transcript).Count -eq 0)

# --- Job one: conversational data entry ---
Write-Host "  ....  conversational data entry (real LLM calls, please wait)" -ForegroundColor DarkGray
$turn = Send-Chat $listing.id "It's in Wailea, Maui - 4 beds, 4.5 baths, asking 8950000."
if ($null -eq $turn) {
  Write-Host "  STOP  the chat endpoint failed. A 502 means the LLM call itself failed:" -ForegroundColor Yellow
  Write-Host "        confirm OPENROUTER_API_KEY reached the app and check the backend log." -ForegroundColor Yellow
  Write-Total " (stopped at the first turn)"; return
}

Check "the turn reports it changed the listing" ($turn.listing_changed -eq $true)
Check "the turn records both sides"             (@($turn.messages).Count -eq 2)

$filled = Invoke-Api "Get" "/api/listings/$($listing.id)" $null
Check "chat recorded the beds"     ($filled.beds -eq 4)
Check "chat recorded the baths"    ($filled.baths -eq 4.5)
Check "chat recorded the price"    ($filled.price -eq 8950000)
Check "chat recorded the location" ($filled.location -like "*Wailea*")
Check "chat left the title alone"  ($filled.title -eq "Oceanfront Villa Kai")

# A question is not a fact: nothing should be written from one.
$before = Invoke-Api "Get" "/api/listings/$($listing.id)" $null
$asked  = Send-Chat $listing.id "What's the square footage on this one?"
Check "a question changes no fields" ($asked.listing_changed -eq $false)
$after = Invoke-Api "Get" "/api/listings/$($listing.id)" $null
Check "the listing is untouched by a question" (
  ($after.interior_sqft -eq $before.interior_sqft) -and ($after.beds -eq $before.beds))

# Follow-ups need the history the server stores.
$followUp = Send-Chat $listing.id "About 4,200."
Check "a follow-up resolves against the transcript" ($followUp.listing_changed -eq $true)
Check "the follow-up landed in the right field" (
  (Invoke-Api "Get" "/api/listings/$($listing.id)" $null).interior_sqft -eq 4200)

$sofar = Invoke-Api "Get" "/api/listings/$($listing.id)/chat" $null
Check "the transcript is accumulating (3 turns, 6 messages)" (@($sofar).Count -eq 6)

# --- Copy edits are refused until there is copy ---
$early = Send-Chat $listing.id "Rewrite the reel script to be punchier."
Check "a copy edit before generating changes no package" ($early.package_changed -eq $false)
Check "and no package was invented" (
  (Get-FailCode "Get" "/api/listings/$($listing.id)/package" $H $null) -eq 404)

# --- Job two: conversational package editing ---
Write-Host "  ....  generating the package to edit (real LLM calls, please wait)" -ForegroundColor DarkGray
$pkg = Invoke-Api "Post" "/api/listings/$($listing.id)/package" $null
if ($null -eq $pkg) {
  Write-Host "  STOP  generation failed - that is Phase 4, not the chat." -ForegroundColor Yellow
  Write-Total " (stopped before the editing checks)"; return
}

$firstCaption = $pkg.captions[0]
$edit = Send-Chat $listing.id "Rewrite the '$($firstCaption.label)' caption - make it much shorter."
Check "the turn reports it changed the package" ($edit.package_changed -eq $true)

$edited = Invoke-Api "Get" "/api/listings/$($listing.id)/package" $null
$newCaption = @($edited.captions | Where-Object { $_.id -eq $firstCaption.id })[0]
Check "the named caption was rewritten" ($newCaption.text -ne $firstCaption.text)
Check "its label was left alone"        ($newCaption.label -eq $firstCaption.label)
Check "the reel script was left alone"  ($edited.reel_script -eq $pkg.reel_script)
Check "the slides were left alone" (
  (@($edited.slides | ForEach-Object { $_.caption }) -join "|") -eq
  (@($pkg.slides   | ForEach-Object { $_.caption }) -join "|"))
Check "the package id did not change"   ($edited.id -eq $pkg.id)
Check "photo bindings survived the edit" (
  (@($edited.slides | ForEach-Object { $_.listing_photo_id }) -join ",") -eq
  (@($pkg.slides   | ForEach-Object { $_.listing_photo_id }) -join ","))

# --- Approval, and what does or does not undo it ---
Invoke-Api "Post" "/api/listings/$($listing.id)/package/approve" $null | Out-Null
Send-Chat $listing.id "Also note there's a detached guest house." | Out-Null
Check "recording a spec leaves an approved package approved" (
  (Invoke-Api "Get" "/api/listings/$($listing.id)/package" $null).status -eq "approved")

$reword = Send-Chat $listing.id "Now rewrite the first carousel slide caption."
Check "a copy rewrite returns it to draft" (
  ($reword.package_changed -eq $true) -and
  ((Invoke-Api "Get" "/api/listings/$($listing.id)/package" $null).status -eq "draft"))

# --- Owner scoping ---
$intruder = Invoke-Api "Post" "/api/auth/signup" (
  @{ email = "intruder+$(Get-Random)@studio.com"; password = "secret123" } | ConvertTo-Json) @{}
$iH = @{ Authorization = "Bearer $($intruder.token)" }
$msg = @{ message = "Set the price to 1." } | ConvertTo-Json

Check "another agent cannot read the transcript" (
  (Get-FailCode "Get"  "/api/listings/$($listing.id)/chat" $iH $null) -eq 404)
Check "another agent cannot post to it" (
  (Get-FailCode "Post" "/api/listings/$($listing.id)/chat" $iH $msg) -eq 404)
Check "chat with no token -> 401" (
  (Get-FailCode "Post" "/api/listings/$($listing.id)/chat" @{} $msg) -eq 401)

Check "the intruder's message changed nothing" (
  (Invoke-Api "Get" "/api/listings/$($listing.id)" $null).price -eq 8950000)

Write-Host ""
Write-Host "  Try the chat in the UI: $base/listings/package/?id=$($listing.id)" -ForegroundColor DarkGray
Write-Host "  Sign in as $email / secret123, then ask it to shorten a caption." -ForegroundColor DarkGray
Write-Total ""
