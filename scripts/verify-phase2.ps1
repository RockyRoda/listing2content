# Phase 2 smoke test: static serving + auth API on http://localhost:8000
# Assumes the app is already running (Docker or uvicorn). Run: .\verify-phase2.ps1
$ErrorActionPreference = "SilentlyContinue"
# Requests use the IPv4 loopback, not "localhost": Windows resolves localhost
# to ::1 first and Docker Desktop's [::]:8000 publish does not forward, so an
# IPv6-first request stalls until it times out.
$base = "http://127.0.0.1:8000"
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

# --- Static frontend is served ---
$root   = Invoke-WebRequest "$base/"          -UseBasicParsing
$signin = Invoke-WebRequest "$base/signin/"   -UseBasicParsing
$signup = Invoke-WebRequest "$base/signup/"   -UseBasicParsing
$dash   = Invoke-WebRequest "$base/dashboard/" -UseBasicParsing
$noslash = Invoke-WebRequest "$base/signin"   -UseBasicParsing
Check "GET / serves the frontend (200 + wordmark)"      (($root.StatusCode -eq 200)   -and ($root.Content   -match "Listing"))
Check "GET /signin/ serves sign-in page"                (($signin.StatusCode -eq 200) -and ($signin.Content -match "Welcome back"))
Check "GET /signup/ serves sign-up page"                (($signup.StatusCode -eq 200) -and ($signup.Content -match "Create your studio"))
Check "GET /dashboard/ serves dashboard shell (200)"    ($dash.StatusCode -eq 200)
Check "GET /signin (no trailing slash) resolves (200)"  ($noslash.StatusCode -eq 200)

# --- Auth API (same origin the frontend calls) ---
$email = "verify+$(Get-Random)@studio.com"
$body  = @{ email = $email; password = "secret123" } | ConvertTo-Json

$su = Invoke-RestMethod -Method Post -Uri "$base/api/auth/signup" -Body $body -ContentType "application/json"
Check "signup returns a user id and token" (($su.user.id -gt 0) -and ($su.token.Length -gt 20))

# Duplicate signup -> 409
$dupCode = 0
try { Invoke-RestMethod -Method Post -Uri "$base/api/auth/signup" -Body $body -ContentType "application/json" } catch { $dupCode = $_.Exception.Response.StatusCode.value__ }
Check "duplicate email signup -> 409" ($dupCode -eq 409)

# Signin with correct creds -> token
$si = Invoke-RestMethod -Method Post -Uri "$base/api/auth/signin" -Body $body -ContentType "application/json"
Check "signin with correct password returns token" ($si.token.Length -gt 20)

# Wrong password -> 401
$wrong = @{ email = $email; password = "nope" } | ConvertTo-Json
$wpCode = 0
try { Invoke-RestMethod -Method Post -Uri "$base/api/auth/signin" -Body $wrong -ContentType "application/json" } catch { $wpCode = $_.Exception.Response.StatusCode.value__ }
Check "signin with wrong password -> 401" ($wpCode -eq 401)

# Protected /auth/me with token -> the user
$me = Invoke-RestMethod -Uri "$base/api/auth/me" -Headers @{ Authorization = "Bearer $($su.token)" }
Check "/auth/me with valid token returns the user" ($me.email -eq $email)

# Protected /auth/me with bad token -> 401
$badCode = 0
try { Invoke-RestMethod -Uri "$base/api/auth/me" -Headers @{ Authorization = "Bearer garbage" } } catch { $badCode = $_.Exception.Response.StatusCode.value__ }
Check "/auth/me with bad token -> 401" ($badCode -eq 401)

# Protected /auth/me with no token -> 401
$noCode = 0
try { Invoke-RestMethod -Uri "$base/api/auth/me" } catch { $noCode = $_.Exception.Response.StatusCode.value__ }
Check "/auth/me with no token -> 401" ($noCode -eq 401)

Write-Host ""
Write-Host "  $pass passed, $fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
