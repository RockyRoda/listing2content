# Seed a demo agent so the interface can be reviewed without setting anything
# up by hand: a voice profile, four listings covering each state the package
# page can be in, and real generated content for two of them.
#
# The database is wiped on every app restart, so re-run this after each start.
# Needs the app running and OPENROUTER_API_KEY reaching it (two real LLM calls,
# ~60s; pass -SkipGeneration to skip them).
#
# Run: .\seed-demo.ps1  [-PhotoDir C:\path\with\jpgs] [-SkipGeneration]
param(
  [string]$PhotoDir = "C:\Windows\Web\Wallpaper\ThemeA",
  [string]$Email = "demo@studio.com",
  [string]$Password = "demo1234",
  [switch]$SkipGeneration
)

$ErrorActionPreference = "SilentlyContinue"
# IPv4 loopback: localhost resolves to ::1 first here and stalls. See
# docs/TEST-PHASE7.md.
$base = "http://127.0.0.1:8000"
$shown = "http://localhost:8000"

# --- The app has to be up ---
$up = $false
for ($i = 0; $i -lt 30; $i++) {
  try { if ((Invoke-RestMethod "$base/health").status -eq "ok") { $up = $true; break } } catch {}
  Start-Sleep -Milliseconds 700
}
if (-not $up) {
  Write-Host "No app at $shown - start it first with .\scripts\start-windows.ps1" -ForegroundColor Yellow
  return
}

$photos = @(Get-ChildItem -Path $PhotoDir -Filter *.jpg | Select-Object -First 3)
if ($photos.Count -lt 2) {
  Write-Host "Need at least 2 .jpg files in $PhotoDir - pass -PhotoDir to point elsewhere." -ForegroundColor Yellow
  return
}

# --- Sign up, or sign in if this account already exists ---
$creds = @{ email = $Email; password = $Password } | ConvertTo-Json
$auth = $null
try {
  $auth = Invoke-RestMethod -Method Post -Uri "$base/api/auth/signup" -Body $creds `
    -ContentType "application/json" -ErrorAction Stop
  Write-Host "  created $Email" -ForegroundColor DarkGray
} catch {
  $auth = Invoke-RestMethod -Method Post -Uri "$base/api/auth/signin" -Body $creds `
    -ContentType "application/json"
  Write-Host "  signed in as existing $Email" -ForegroundColor DarkGray
}
if (-not $auth) { Write-Host "Could not sign up or sign in." -ForegroundColor Red; return }
$H = @{ Authorization = "Bearer $($auth.token)" }
$bearer = "Authorization: Bearer $($auth.token)"

# --- A voice profile: terse and concrete, so its effect is visible in the copy ---
$voiceFile = Join-Path $env:TEMP "l2c-demo-voice-$(Get-Random).txt"
@"
The light here does the selling. Stand on the lanai at seven and you will see it.
Four bedrooms. Two of them open straight onto the water.
The kitchen is for cooking, not for photographing. It still photographs well.
No lawn to mow. No commute. The reef is a two minute walk and it is always there.
Bring an offer. Bring your architect if you want, but you will not change much.
"@ | Out-File -FilePath $voiceFile -Encoding utf8
& curl.exe -s -X PUT "$base/api/voice-profile" -H $bearer `
  -F "files=@$voiceFile;type=text/plain" `
  -F "tone_notes=Unhurried and concrete. Short sentences. Never breathless." | Out-Null
Remove-Item $voiceFile -Force
Write-Host "  uploaded a voice profile" -ForegroundColor DarkGray

function New-Listing($fields) {
  return Invoke-RestMethod -Method Post -Uri "$base/api/listings" `
    -Body ($fields | ConvertTo-Json) -ContentType "application/json" -Headers $H
}

function Add-Photos($listingId, $count) {
  $curlArgs = @("-s", "-X", "POST", "$base/api/listings/$listingId/photos", "-H", $bearer)
  foreach ($p in ($photos | Select-Object -First $count)) {
    $curlArgs += @("-F", "files=@$($p.FullName);type=image/jpeg")
  }
  & curl.exe @curlArgs | Out-Null
}

# --- Four listings, one for each state the package page can be in ---
$villa = New-Listing @{
  title = "Oceanfront Villa Kai"; location = "Wailea, Maui"; price = 8950000
  beds = 4; baths = 4.5; interior_sqft = 4200; lot_size = "0.6 acres"
  property_type = "Single-family"; mls_number = "MLS-401882"
  features = "Infinity pool, outdoor kitchen, private beach path, solar"
  description = "Sits low on the point where the trade winds come across."
}
Add-Photos $villa.id 3

$hale = New-Listing @{
  title = "Hillside Hale"; location = "Kula, Maui"; price = 3400000
  beds = 3; baths = 3.0; interior_sqft = 2600; property_type = "Single-family"
  mls_number = "MLS-397145"; features = "Upcountry views, cedar deck, orchard"
}
Add-Photos $hale.id 2

$ridge = New-Listing @{
  title = "Sunset Ridge Estate"; location = "Kapalua, Maui"; price = 12750000
  beds = 6; baths = 6.5; interior_sqft = 7100; property_type = "Estate"
  features = "Guest hale, tennis court, ocean and mountain views"
}
Add-Photos $ridge.id 2

$bare = New-Listing @{
  title = "Bare Lot at Kapalua"; location = "Kapalua, Maui"; price = 1950000
  lot_size = "1.2 acres"; property_type = "Land"
  features = "Ridge parcel, approved plans available"
}

Write-Host "  created 4 listings" -ForegroundColor DarkGray

# --- Generate for two of them, and approve one ---
$villaState = "none"; $haleState = "none"
if ($SkipGeneration) {
  Write-Host "  skipping generation (-SkipGeneration)" -ForegroundColor DarkGray
} else {
  Write-Host "  ....  generating for 2 listings (real LLM calls, ~60s)" -ForegroundColor DarkGray
  try {
    Invoke-RestMethod -Method Post -Uri "$base/api/listings/$($villa.id)/package" `
      -Headers $H -ErrorAction Stop | Out-Null
    $villaState = "draft"
  } catch {
    Write-Host "        generation failed for the villa: HTTP $($_.Exception.Response.StatusCode.value__)" -ForegroundColor DarkYellow
  }
  try {
    Invoke-RestMethod -Method Post -Uri "$base/api/listings/$($hale.id)/package" `
      -Headers $H -ErrorAction Stop | Out-Null
    Invoke-RestMethod -Method Post -Uri "$base/api/listings/$($hale.id)/package/approve" `
      -Headers $H -ErrorAction Stop | Out-Null
    $haleState = "approved"
  } catch {
    Write-Host "        generation failed for the hale: HTTP $($_.Exception.Response.StatusCode.value__)" -ForegroundColor DarkYellow
  }
}

# --- What to do with it ---
$rows = @(
  [pscustomobject]@{ Listing = $villa.title; Id = $villa.id; Photos = 3; Package = $villaState
    Try = "Edit a caption, Save, reload - it should persist" }
  [pscustomobject]@{ Listing = $hale.title; Id = $hale.id; Photos = 2; Package = $haleState
    Try = "Edit it - the badge should drop back to Draft" }
  [pscustomobject]@{ Listing = $ridge.title; Id = $ridge.id; Photos = 2; Package = "none"
    Try = "Click Generate package (real LLM, ~30s)" }
  [pscustomobject]@{ Listing = $bare.title; Id = $bare.id; Photos = 0; Package = "none"
    Try = "Generate - expect the add-a-photo warning" }
)

Write-Host ""
Write-Host "  Sign in at $shown" -ForegroundColor Cyan
Write-Host "    email:    $Email"
Write-Host "    password: $Password"
Write-Host ""
$rows | Format-Table -AutoSize Listing, Id, Photos, Package, Try
Write-Host "  Package pages:" -ForegroundColor DarkGray
foreach ($r in $rows) {
  Write-Host "    $($r.Listing): $shown/listings/package/?id=$($r.Id)" -ForegroundColor DarkGray
}
Write-Host "    Voice profile: $shown/settings" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  The database is wiped when the app restarts - re-run this script after each start." -ForegroundColor DarkGray
