# Testing Listing2Content

Everything here runs offline except the `verify-phase*` smoke tests, which need
a running app and a real `OPENROUTER_API_KEY`.

---

## Backend suite — offline, no key, ~12s

```bash
cd backend
uv run pytest                                      # 73 tests
uv run pytest --cov=app --cov-report=term-missing  # with coverage
```

Expect **73 passed** and **100% statement coverage** of `backend/app`.

| File | Covers |
| --- | --- |
| `test_auth.py` | Signup, signin, token lookup, 401s |
| `test_listings.py` | Listing CRUD, photo upload validation (type/size/count), delete |
| `test_voice_profiles.py` | Sample upload, style distillation, the 1 MB cap, contamination guard |
| `test_content_packages.py` | Generation endpoint, photo mapping, edit/approve, package scoping |
| `test_generation.py` | **The LLM module itself** — prompt building, structured-output parsing, model routing, captioning cap and order |
| `test_integration_flow.py` | The whole product in one pass: signup → voice → listing → photos → generate → edit → approve → reload, plus agent isolation and `/health` |

The LLM is always stubbed. `test_generation.py` and `test_integration_flow.py`
stub one level lower than the rest — at litellm's `completion` — so the real
prompt construction and real Pydantic parsing run. Everywhere else
`app.generation` is replaced wholesale.

---

## Browser tests — offline, no key, ~7s

```bash
cd frontend
npm run build     # the backend serves this export
npm run e2e       # 7 tests
```

First run only: `npx playwright install chromium`.

`e2e/package-review.spec.ts` drives the review pass in a real Chromium: the
draft/approved badge, which buttons are live when, the dirty-state warning, the
exact shape of the PUT the editor sends, that an edit survives a reload, and
that typing does not refetch the slide photos.

Every `/api/**` call is mocked in the browser, so no key, no LLM, and no
database are involved — the API is already covered above. The backend runs on
port 8123 purely as the static file server, which is what serves the export in
production.

---

## Smoke tests — running app + real key

These make real LLM calls and cost API credit. Each assumes the app is already
up unless noted.

| Script | What it checks | Expect |
| --- | --- | --- |
| `scripts/verify-phase2.ps1` | Static serving and the auth API | all pass |
| `scripts/verify-phase4.ps1` | Generation, photo captioning, voice shaping, prompt-leak guards | all pass |
| `scripts/verify-phase5.ps1` | Review/edit/approve over HTTP | 24 passed |
| `scripts/verify-phase7.ps1` | Docker packaging; **drives the start/stop scripts itself** | 27 passed |

Longer walkthroughs live in `docs/TEST-PHASE5.md` and `docs/TEST-PHASE7.md`.

All four probe `http://127.0.0.1:8000`, not `localhost` — Windows resolves
`localhost` to `::1` first and Docker Desktop's `[::]:8000` publish does not
forward, so an IPv6-first request stalls until it times out. See
`docs/TEST-PHASE7.md`.

---

## What is still not covered

- **The mac and linux start/stop scripts have never run on real macOS or
  Linux** — only on Windows through Git Bash, plus `bash -n`. The one gap that
  needs a machine we do not have.
- **No CI.** Everything above is run by hand; there are no GitHub Actions
  workflows.
- **The AI's output quality** is only checked structurally (a package parses,
  has slides, and does not leak the voice sample's facts). Whether the copy is
  any good is a human judgement, and the `verify-phase4.ps1` voice checks are
  the closest thing to a proxy.
- **Frontend pages other than the package editor** — sign-in, listing form,
  settings — have no browser tests; they are exercised by hand.
