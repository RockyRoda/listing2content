# Phase 8 smoke test: does the test suite actually bite?
#
# A green suite proves nothing on its own - a test that cannot fail passes too.
# This runs the suite, then breaks the code in known ways and checks that the
# tests we claim cover each behaviour DO fail. Every mutation is reverted with
# `git checkout --`, so nothing is left behind even if this is interrupted.
#
# Needs no API key, no Docker, and no running app.
# Run: .\verify-phase8.ps1  [-IncludeBrowser]
param([switch]$IncludeBrowser)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$pass = 0; $fail = 0

function Check($name, $cond) {
  if ($cond) { Write-Host "  PASS  $name" -ForegroundColor Green; $script:pass++ }
  else       { Write-Host "  FAIL  $name" -ForegroundColor Red;   $script:fail++ }
}

# Refuse to run over uncommitted work: mutations are reverted with git, which
# would discard it.
$dirty = & git -C $root status --porcelain -- backend frontend
if ($dirty) {
  Write-Host "Uncommitted changes in backend/ or frontend/:" -ForegroundColor Yellow
  $dirty | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
  Write-Host "This script reverts files with 'git checkout --', which would discard them." -ForegroundColor Yellow
  Write-Host "Commit or stash first." -ForegroundColor Yellow
  return
}

function Invoke-Pytest($testArgs) {
  Push-Location $backend
  try { $out = & uv run pytest $testArgs -q 2>&1 | Out-String }
  finally { Pop-Location }
  return $out
}

# Writes text without the BOM that Set-Content -Encoding utf8 would add in
# PowerShell 5.1 - a BOM would change the file's bytes, not just its content.
function Write-NoBom($path, $text) {
  [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

# Applies one mutation, runs the named tests, and expects them to FAIL.
function Test-Mutation($name, $relPath, $find, $replace, $testArgs) {
  $full = Join-Path $root $relPath
  $before = [System.IO.File]::ReadAllText($full)
  $after = $before.Replace($find, $replace)
  if ($after -eq $before) {
    Check "$name (mutation applied)" $false
    Write-Host "        pattern not found in $relPath - the code moved on" -ForegroundColor DarkYellow
    return
  }
  try {
    Write-NoBom $full $after
    $out = Invoke-Pytest $testArgs
    $caught = $out -match "\d+ failed"
    Check "$name" $caught
    if (-not $caught) {
      Write-Host "        the suite stayed green with broken code" -ForegroundColor DarkYellow
    }
  } finally {
    & git -C $root checkout -- $relPath
  }
}

Write-Host ""
Write-Host "  Baseline" -ForegroundColor Cyan
$baseline = Invoke-Pytest @()
Check "suite is green to start with" ($baseline -match "\d+ passed" -and $baseline -notmatch "failed")
if ($baseline -match "(\d+) passed") { Write-Host "        $($Matches[1]) tests" -ForegroundColor DarkGray }

$cov = Invoke-Pytest @("--cov=app", "--cov-report=term")
Check "app/ is fully covered" ($cov -match "TOTAL\s+\d+\s+0\s+100%")

Write-Host ""
Write-Host "  Mutations - each SHOULD be caught" -ForegroundColor Cyan

# 1. The bug that the old suite could not see: captions attached to the wrong
#    photos. Every test passed with this in place before Phase 8.
Test-Mutation "caption/photo mis-mapping is caught" `
  "backend/app/generation.py" `
  "descriptions = list(pool.map(lambda photo: describe_photo(*photo), capped))" `
  "descriptions = list(pool.map(lambda photo: describe_photo(*photo), capped))[::-1]" `
  @("tests/test_generation.py")

# 2. The voice-contamination invariant from docs/VOICE-CONTAMINATION.md: the
#    raw writing samples must never reach the assembly prompt.
Test-Mutation "voice sample leaking into the prompt is caught" `
  "backend/app/content_packages.py" `
  'voice["style_notes"] if voice else ""' `
  'voice["sample_text"] if voice else ""' `
  @("tests/test_integration_flow.py", "tests/test_voice_profiles.py")

# 3. The empty-photo crash fixed in Phase 8. Single-line patterns only: .py
#    files check out with CRLF on Windows, so an embedded \n would never match.
Test-Mutation "the empty-photo crash is caught" `
  "backend/app/generation.py" `
  "    if capped:" `
  "    if True:" `
  @("tests/test_generation.py")

# 4. Cross-package writes: dropping the scoping clause would let one package's
#    edit overwrite another's caption.
Test-Mutation "cross-package caption writes are caught" `
  "backend/app/content_packages.py" `
  '"UPDATE captions SET text = ? WHERE id = ? AND content_package_id = ?"' `
  '"UPDATE captions SET text = ? WHERE id = ? AND ? IS NOT NULL"' `
  @("tests/test_content_packages.py")

# 5. Approval must not survive an edit.
Test-Mutation "approval surviving an edit is caught" `
  "backend/app/content_packages.py" `
  "UPDATE content_packages SET reel_script = ?, status = 'draft' WHERE id = ?" `
  "UPDATE content_packages SET reel_script = ? WHERE id = ?" `
  @("tests/test_content_packages.py")

# 6. Photo captioning must stay capped, or a 20-photo listing costs 20 calls.
Test-Mutation "removing the captioning cap is caught" `
  "backend/app/generation.py" `
  "capped = photos[:MAX_CAPTIONED_PHOTOS]" `
  "capped = photos[:]" `
  @("tests/test_generation.py")

if ($IncludeBrowser) {
  Write-Host ""
  Write-Host "  Browser specs" -ForegroundColor Cyan
  $frontend = Join-Path $root "frontend"
  Push-Location $frontend
  try {
    & npm run build 2>&1 | Out-Null
    $e2e = & npx playwright test 2>&1 | Out-String
    Check "playwright specs pass" ($e2e -match "\d+ passed" -and $e2e -notmatch "\d+ failed")

    # The photo-refetch optimisation: keying the memo on the mutating copy
    # refetches every photo on each keystroke.
    $editor = Join-Path $root "frontend/components/PackageEditor.tsx"
    $before = [System.IO.File]::ReadAllText($editor)
    try {
      Write-NoBom $editor $before.Replace("[initial.slides],", "[pkg.slides],")
      & npm run build 2>&1 | Out-Null
      $broken = & npx playwright test -g "refetch" 2>&1 | Out-String
      Check "photo refetch regression is caught" ($broken -match "\d+ failed")
    } finally {
      & git -C $root checkout -- "frontend/components/PackageEditor.tsx"
      & npm run build 2>&1 | Out-Null
    }
  } finally { Pop-Location }
} else {
  Write-Host ""
  Write-Host "  SKIP  browser specs - pass -IncludeBrowser to include them" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Final check" -ForegroundColor Cyan
$restored = Invoke-Pytest @()
Check "every mutation was reverted (suite green again)" (
  $restored -match "\d+ passed" -and $restored -notmatch "failed")
$leftover = & git -C $root status --porcelain -- backend frontend
Check "no files left modified" (-not $leftover)
if ($leftover) { $leftover | ForEach-Object { Write-Host "        $_" -ForegroundColor Red } }

Write-Host ""
Write-Host "  $pass passed, $fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
