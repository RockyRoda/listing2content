# Testing Phase 7 — Docker packaging & scripts

Phase 7 hardened the container build and the six start/stop scripts. Four
levels, cheapest first.

Level 1 needs only the repo. Levels 2–4 need Docker Desktop running and a
`.env` holding a real `OPENROUTER_API_KEY`.

---

## 1. Repo checks — no Docker, no key, instant

```powershell
.\scripts\verify-phase7.ps1
```

Run this in a checkout with **no** `.env` and it does the repo and guard checks
only, then says `SKIP container checks`. Expect `6 passed, 0 failed`:

| Check | Why it matters |
| --- | --- |
| `.env.example` is committed | A fresh clone needs a template; without it there is nothing to copy |
| `.env.example` names `OPENROUTER_API_KEY` | The template is useful, not empty |
| `.env` itself is NOT committed | The key must never enter git |
| `.dockerignore` excludes `.env` | The key must never enter the image |
| Missing `.env` stops the script with guidance | The clean-checkout first run |
| Missing `.env` never reaches `docker build` | It fails fast, not after a 3-minute build |

---

## 2. Full smoke test — Docker + key, a few minutes

```powershell
.\scripts\verify-phase7.ps1
```

With a `.env` present, expect **`27 passed, 0 failed`**. It drives the real
scripts, so it rebuilds the image and replaces any running container. Nothing
is lost — the DB and photos are ephemeral by design (decision 13).

It makes one real LLM call, and it leaves the app **stopped** when it finishes.

What it proves beyond level 1:

- `start` exits 0, waits for readiness rather than guessing, and publishes 8000
- The key **reaches the running container** but is **absent from the image**,
  and no `.env` is inside it
- Frontend index and a deep route are both served out of the image
- The container's `HEALTHCHECK` reports `healthy`
- A new agent starts with no listings, and **a real generation succeeds inside
  the container** — the plan's stated validation
- A second `start` is idempotent: it replaces the container, the app comes
  back, and the previous session 401s
- `stop` removes the container and honestly says `was not running` the second
  time

---

## 3. Clean-checkout test — the plan's literal validation

This is the one thing level 2 only simulates (it runs the guard from a
throwaway directory). Here you clone for real, which also confirms the `755`
bits on the shell scripts survive a clone.

```powershell
# 1. Clone somewhere temporary
$clean = Join-Path $env:TEMP "l2c-clean"
git clone -b main https://github.com/RockyRoda/listing2content.git $clean

# 2. No .env yet -> expect the guidance and exit 1, with no build
& powershell -NoProfile -File "$clean\scripts\start-windows.ps1"
$LASTEXITCODE      # expect 1

# 3. Add your key, then start for real
Copy-Item "$clean\.env.example" "$clean\.env"
notepad "$clean\.env"        # paste your OPENROUTER_API_KEY, save

& powershell -NoProfile -File "$clean\scripts\start-windows.ps1"
$LASTEXITCODE      # expect 0, after "Listing2Content running at ..."

# 4. Clean up - this directory holds a copy of your key
& powershell -NoProfile -File "$clean\scripts\stop-windows.ps1"
Remove-Item $clean -Recurse -Force
```

Expected at step 2:

```
No .env found at C:\...\l2c-clean\.env
Copy .env.example to .env and add your OPENROUTER_API_KEY, then run this again.
```

**Don't forget step 4.** That checkout contains your API key in plain text.

---

## 4. Browser and by-hand checks

With the app running (`.\scripts\start-windows.ps1`):

| Do this | Expect |
| --- | --- |
| Open http://localhost:8000 | The sign-in page, served out of the image — proves the static export shipped inside the container |
| Sign up as a new agent | Lands on the dashboard; a brand-new container has no accounts, so any email works |
| `docker ps` | `Up ... (healthy)` and `0.0.0.0:8000->8000/tcp` |
| `docker exec listing2content printenv OPENROUTER_API_KEY` | Your key — it reached the container at run time |
| `docker image inspect listing2content --format '{{json .Config.Env}}'` | **No** `OPENROUTER_API_KEY` — it is not baked into the image |
| `docker run --rm --entrypoint sh listing2content -c "ls -a /app"` | `backend frontend` only — no `.env` |
| `.\scripts\stop-windows.ps1` then `docker ps -a` | No `listing2content` container |
| Run `stop` a second time | `Listing2Content was not running` |

### Why the scripts probe 127.0.0.1

You can see the problem that drove this yourself:

```powershell
Invoke-WebRequest "http://127.0.0.1:8000/health" -UseBasicParsing   # {"status":"ok"}
Invoke-WebRequest "http://[::1]:8000/health" -TimeoutSec 4          # times out
[System.Net.Dns]::GetHostAddresses("localhost")                     # ::1 listed first
```

`localhost` resolves to `::1` first, and Docker Desktop's `[::]:8000` publish
does not forward, so an IPv6-first readiness probe stalls on every attempt
while the container sits there healthy. `curl` hides this by falling back to
IPv4; PowerShell's `Invoke-RestMethod` does not. The scripts therefore probe
`127.0.0.1` and only *display* the `localhost` URL, which browsers resolve fine.

---

## 5. The Unix scripts

`start-mac.sh` / `start-linux.sh` / `stop-mac.sh` / `stop-linux.sh` delegate to
`start-unix.sh` / `stop-unix.sh`. On Windows you can still exercise them through
Git Bash, since the Docker CLI is on PATH there:

```bash
./scripts/stop-linux.sh     # "Listing2Content was not running"
./scripts/start-mac.sh      # builds, waits, "Listing2Content running at ..."
./scripts/stop-mac.sh       # "Listing2Content stopped"
```

**Caveat:** these have been run on Windows via Git Bash and syntax-checked with
`bash -n`, but **never on real macOS or Linux**. If you have access to either,
that is the one gap worth closing by hand.

---

## What is deliberately not covered

- **No `docker-compose.yml`.** Decision 12: the start scripts call
  `docker run --env-file .env` directly.
- **No persistence.** Every restart wipes the DB, photos, and sessions
  (decision 13). The smoke test asserts this rather than working around it.
- **No multi-arch or registry push.** The image is built and run locally.
- **`verify-phase4.ps1` and `verify-phase5.ps1` still probe `localhost`.** They
  pass today because they do not set short timeouts, so .NET falls back to
  IPv4, but they are exposed to the stall described above.
