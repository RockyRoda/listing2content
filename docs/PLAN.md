# Listing2Content — Master Plan

## Product summary
SaaS tool for luxury/resort real estate agents. Agent inputs a new listing
(photos, specs/features, MLS details); the app drafts a full content package
(carousel, caption set, Reel script) in the agent's voice with resort-market
lifestyle framing, ready for a quick approve/edit pass. An AI chat lets the
agent both feed in listing data conversationally and edit/save the generated
package.

## Current repo state
Greenfield. Only `CLAUDE.md`, `README.md`, `LICENSE`, `.gitignore`, `.env`
(with `OPENROUTER_API_KEY`) exist. No `backend/`, `frontend/`, `scripts/`,
or `docs/` yet.

## Target architecture (per CLAUDE.md + decisions below)
- `backend/` — FastAPI, managed with `uv`
- `frontend/` — Next.js, static export, served by FastAPI's static file
  handling
- SQLite DB, recreated from scratch on each container startup; `users` and
  `sessions` tables
- Auth: opaque server-side bearer tokens, not JWT. `backend/app/auth.py`
  generates a random 32-byte URL-safe token (`secrets.token_urlsafe(32)`) on
  signup/signin, stores it in a `sessions` table (`token`, `user_id`).
  Protected routes depend on `get_current_user_id`, which reads the
  `Authorization: Bearer <token>` header, looks it up in `sessions`, and
  returns the `user_id` (401 if missing/not found). No expiry, refresh, or
  logout/revoke endpoint — tokens are only valid until the process restarts,
  since the DB (and therefore `sessions`) is wiped and recreated on every
  backend startup anyway. Frontend stores `{user, token}` in `localStorage`
  and sends it back as the `Authorization: Bearer` header.
- Listing photos: ephemeral, stored in the container filesystem. Lost on
  rebuild/restart — consistent with the DB's fresh-start behavior. No
  mounted volume for v1.
- LLM calls, two steps:
  1. **Vision captioning** — each listing photo is described by a
     vision-capable model via plain OpenRouter/LiteLLM (not the Cerebras
     provider, which doesn't serve vision for `gpt-oss-120b`). Specific
     model TBD at Phase 4 implementation time. Output: text description per
     photo.
  2. **Content assembly** — via the `cerebras` skill: LiteLLM -> OpenRouter
     -> `openai/gpt-oss-120b` on Cerebras, Structured Outputs (Pydantic),
     fed the listing specs + voice profile + per-photo captions from step 1
- Content package schema: `content_packages` (id, listing_id, status
  `draft`/`approved`, generated_at, reel_script text), `carousel_slides`
  (id, content_package_id, listing_photo_id, order_index, caption),
  `captions` (id, content_package_id, label, text) — see Phase 4
- Whole app packaged as one Docker container; `OPENROUTER_API_KEY` reaches
  it via `docker run --env-file .env` (no `docker-compose.yml`)
- `scripts/start-*.{sh,ps1}` / `stop-*.{sh,ps1}` for mac/linux/windows
- All planning docs live in `docs/`

## Timeline note
README states target completion 2026-07-28 (5 days from today, 2026-07-23).
That's tight — the phase order below is chosen so the app is
demoable end-to-end early (Phase 4), with chat-based editing (Phase 6)
explicitly scoped as a stretch goal to add only after the core
auth -> listing -> generate -> review/edit -> Docker -> test flow (Phases
0–5, 7–8) is solid.

---

## Phase 0 — Scaffolding
- Create `backend/` as a `uv` project (FastAPI, uvicorn added via `uv add`)
- Create `frontend/` (framework TBD — see open questions)
- Create `scripts/` with placeholder start/stop scripts for mac/linux/windows
- Create `Dockerfile` (no `docker-compose.yml` — single container, env vars
  passed at run time via `docker run --env-file .env`)
- Spike: one hardcoded prompt + Pydantic schema through the `cerebras` skill
  (LiteLLM -> OpenRouter -> `gpt-oss-120b` on Cerebras) to confirm
  Structured Outputs actually round-trip, before Phase 4 builds on it
- Validate: `uv run` starts a bare FastAPI app with a `/health` endpoint;
  container builds and runs it; the spike call returns a parsed Pydantic
  object

## Phase 1 — Auth & users
- SQLite schema: `users` table (id, email, hashed password, created_at) and
  `sessions` table (token, user_id)
- DB created fresh on each container startup (`db.py` init, per CLAUDE.md)
- Password hashing via `argon2-cffi` (`uv add argon2-cffi`): `ph.hash()` on
  signup, `ph.verify()` on signin
- `backend/app/auth.py`: signup/signin generate an opaque
  `secrets.token_urlsafe(32)` token and insert it into `sessions`;
  `get_current_user_id` dependency reads `Authorization: Bearer <token>`,
  looks it up, 401s if missing/unknown
- No expiry/refresh/logout endpoint for v1 — tokens die with the process
  restart along with the rest of the DB
- Validate: create a user, log in, hit a protected endpoint with the token,
  confirm a bad/missing token 401s

## Phase 2 — Frontend shell
- Scaffold Next.js app (`output: "export"`), wire the static export into
  FastAPI's static file serving
- Sign up / sign in pages calling Phase 1 endpoints, storing `{user, token}`
  in `localStorage` and attaching it as `Authorization: Bearer` on requests
- Validate: full browser signup -> login -> land on an authenticated
  placeholder dashboard, refresh the page and confirm the session persists
  via `localStorage`

## Phase 3 — Listing data model, ingestion & voice profile
- DB schema: `listings` (specs, features, MLS details, owner/user_id) and
  `listing_photos` (file refs)
- DB schema: `voice_profiles` (user_id, tone/style fields, sample_text) —
  one reusable profile per agent, editable any time (not locked at
  creation, not re-entered per listing). Source is user-uploaded `.txt`
  file(s): server reads and concatenates the uploaded text into
  `sample_text`; no separate free-text entry form
- Photos stored on the container filesystem (ephemeral — gone on
  rebuild/restart, same lifecycle as the DB); no mounted volume for v1
- Photo upload validation: content-type allowlist (jpeg/png/webp) and a max
  file size, rejected with 4xx otherwise
- Endpoints: create/read/update listing, upload photos, upload/replace
  voice-profile text file(s)
- Minimal UI: a form to enter a listing and upload photos; a settings page
  to upload/replace the voice-profile text file
- Validate: create a listing with photos, retrieve it back via API and UI;
  upload a voice-profile text file and confirm the extracted text persists;
  confirm an oversized/wrong-type photo upload is rejected

## Phase 4 — AI content generation (core value, ship this early)
- DB schema: `content_packages` (id, listing_id, status `draft`/`approved`,
  generated_at, reel_script text), `carousel_slides` (id,
  content_package_id, listing_photo_id, order_index, caption), `captions`
  (id, content_package_id, label, text)
- Step 1 — vision captioning: for each `listing_photo`, call a
  vision-capable model via OpenRouter/LiteLLM (non-Cerebras; model chosen
  at implementation time) to get a text description
- Step 2 — content assembly: Structured Output schemas (Pydantic) for the
  content package (carousel slides referencing `listing_photo_id`, caption
  set, Reel script); prompt injects listing data + photo captions from
  step 1 + the agent's `voice_profiles.sample_text` + resort-market
  lifestyle framing; call via the `cerebras` skill pattern
- Generation endpoint runs both steps and writes a new `content_packages`
  row (status `draft`) plus its slides/captions
- Minimal UI to trigger generation and display the raw package
- Validate: real listing + photos in -> per-photo captions generated ->
  structured, on-brand package out referencing the right photos, displayed
  in the UI

## Phase 5 — Review / approve / edit pass
- UI to review each piece of the package (carousel/captions/script),
  edit inline, and save
- Endpoints to update `carousel_slides.caption` / `captions.text` /
  `content_packages.reel_script`, and flip `content_packages.status` from
  `draft` to `approved`
- Validate: generate a package, edit a caption, save, reload and confirm
  the edit persisted

## Phase 6 — AI chat (data entry + editing)
- Chat endpoint that can (a) parse conversational input into listing fields
  and (b) apply conversational edit instructions to an existing package
- Chat UI wired to that endpoint, scoped to a listing
- Validate: use chat to fill in a listing field and to request an edit to a
  generated caption; confirm both persist

## Phase 7 — Docker packaging & scripts
- Finalize single-container Docker build (backend serving built frontend,
  SQLite inside container)
- `OPENROUTER_API_KEY` reaches the container via `docker run --env-file
  .env`; each start script (`start-mac.sh`, `start-linux.sh`,
  `start-windows.ps1`) builds/runs the image with that flag directly — no
  `docker-compose.yml`, and `.env` is never copied into the image
- Finish `scripts/start-mac.sh`, `stop-mac.sh`, `start-linux.sh`,
  `stop-linux.sh`, `start-windows.ps1`, `stop-windows.ps1`
- Validate: on a clean checkout, the start script brings up the app at
  `http://localhost:8000` with a fresh DB, and a generation call succeeds
  (proving the API key made it into the container)

## Phase 8 — Testing & hardening
- Unit tests: auth, listing CRUD, structured-output parsing
- Integration tests: signup -> listing -> generate -> edit -> save flow
- Fix issues found; keep changes incremental per CLAUDE.md guidance
- Validate: test suite green via `uv run pytest`

## Phase 9 — Wrap-up
- Update `README.md` (concise, per CLAUDE.md)
- Final pass through `docs/PLAN.md` to mark completed phases
- Open PR per the standard dev process in CLAUDE.md

---

## Decisions (resolved)
1. **Frontend framework** — Next.js, static export, served by FastAPI.
2. **Auth mechanism** — opaque bearer token (`secrets.token_urlsafe(32)`)
   in a `sessions` table, not JWT; no expiry/refresh/logout for v1; frontend
   keeps `{user, token}` in `localStorage`.
3. **Photo storage** — ephemeral, container filesystem only; no persistent
   volume for v1.
4. **Chat scope** — stretch goal. Phases 0–5, 7–8 (auth, listings,
   generation, manual review/edit, Docker, tests) are the v1 target; Phase 6
   (AI chat for data entry/editing) ships only if time allows.

## Decisions (round 2, resolved)
5. **"Agent's voice"** — a reusable profile per agent (`voice_profiles`,
   keyed by `user_id`), editable any time rather than fixed at setup or
   re-entered per listing. See Phase 3.
6. **Next.js static export + bearer-token auth** — confirmed: pure
   client-side auth (`localStorage` + `fetch` headers, no cookies). Next.js
   stays a plain static export with client components gating protected
   pages; no server-side auth checks or middleware.

## Decisions (round 3, resolved — 2026-07-23)
7. **Photos + generation** — content generation does use the actual
   photos, via a vision-captioning pre-step (separate vision-capable model
   over plain OpenRouter, not Cerebras) feeding text descriptions into the
   existing `gpt-oss-120b`/Cerebras structured-output call. See Phase 4.
8. **Carousel ↔ photo mapping** — each `carousel_slides` row references a
   specific `listing_photos` row (`listing_photo_id`, `order_index`).
9. **Content package persistence** — `content_packages` / `carousel_slides`
   / `captions` tables, defined in Phase 4 rather than left implicit until
   Phase 5.
10. **Voice profile input** — agent uploads `.txt` file(s); server extracts
    and concatenates the text into `voice_profiles.sample_text`. No
    free-text paste form.
11. **Password hashing** — `argon2-cffi`. See Phase 1.
12. **`OPENROUTER_API_KEY` at runtime** — `docker run --env-file .env`,
    called directly from each start script; no `docker-compose.yml`.
13. **Data loss on restart** — confirmed acceptable for v1 (DB wipe +
    ephemeral photos + session loss on every restart/redeploy). Revisit
    this decision before any real users are expected to keep data across
    sessions.

No open questions remain. Ready to begin Phase 0 on your go-ahead.

---

## Doc review — questions, clarifications, simplification (2026-07-23)

_Resolved 2026-07-23 — see "Decisions (round 3, resolved)" above and the
phase updates throughout this doc for how each item was incorporated._

### Questions / clarifications needed
1. **Photos + generation** — does the content-generation step (Phase 4) see
   the actual photos (vision-capable call) or only text specs/features? If
   photos matter for captioning/carousel copy, `openai/gpt-oss-120b` needs to
   support image input via OpenRouter/Cerebras — worth confirming before
   Phase 4, not during it, since it changes the prompt design and possibly
   the model choice. Answer: Yes, the content-generation step sees the actual photos
2. **Carousel ↔ photo mapping** — is a carousel slide just generated text, or
   does each slide reference a specific `listing_photos` row (ordering,
   photo-to-copy pairing)? This affects the Phase 4 schema and the Phase 5
   edit UI (can you reorder/reassign photos, or only edit text?). Answer: Each slide references a specific `listing_photos` row
3. **Content package persistence** — Phase 4 says "display the raw package,"
   Phase 5 says "persist edits" and "track approved vs. draft state," but no
   phase defines the actual table (e.g. `content_packages`: id, listing_id,
   status, generated_at, plus child rows or JSON blobs for
   slides/captions/script). Worth pinning down the shape before Phase 4 so
   Phase 5 isn't a retrofit. Answer: Yes, phase 4 is "raw" because it happens before the edits in phase 5
4. **Voice profile input format** — "sample copy/captions" in
   `voice_profiles` — free text the agent pastes in, or something
   structured? Affects the Phase 3 settings-page UI. Answer: User Must provide text files as source for the 'voice_profile'
5. **Password hashing** — schema says "hashed password" but no library is
   named. Worth picking one explicitly (e.g. `argon2-cffi`, latest-API
   default) so Phase 1 doesn't stall on a mid-implementation choice. Answer: Stick with `argon2-cffi`
6. **`OPENROUTER_API_KEY` at container runtime** — `.env` exists at the repo
   root for local `uv run`, but Phase 7's Docker packaging doesn't say how
   the key reaches the running container (`docker run --env-file`,
   `docker-compose.yml` `env_file:`, etc.). Worth a one-line decision so
   Phase 7 isn't guessing. Answer: "docker run --env-file .env — the start scripts (start-mac.sh, start-linux.sh, start-windows.ps1) call docker run --env-file .env ... directly."
7. **Full data loss on every restart, now for a real product** — DB wipe +
   ephemeral photos + no session persistence is reasonable for a fast v1,
   but it means any crash, redeploy, or host reboot deletes every agent's
   listings, voice profile, and generated packages, not just "demo" resets.
   Worth an explicit confirmation that this is acceptable through v1 (and a
   one-line note on when it stops being acceptable), since it's easy to
   forget this is still true once the product feels real to early users. Answer: yes this is acceptble for version1
8. **Timeline drift** — the "Timeline note" section says "~6 days from
   today, 2026-07-22" targeting 2026-07-28. Today is 2026-07-23, so that's
   now 5 days out; the note itself is a day stale. Not urgent, but worth
   updating so it doesn't silently mislead whoever reads it next. Answer: the date is arbitrary, please adjust to makie correct.

### Simplification opportunities
- **De-risk the LLM call before Phase 4** — the Cerebras/OpenRouter/
  structured-output path is the riskiest external dependency and the core
  value prop, but it's currently first exercised deep into Phase 4 alongside
  real listing/voice-profile data. A 10-minute spike in Phase 0 or 1 (one
  hardcoded prompt, one Pydantic schema, confirm structured output actually
  comes back through OpenRouter -> Cerebras -> `gpt-oss-120b`) would surface
  integration surprises early instead of mid-Phase-4. Proceed
- **Photo upload validation** — no mention of file-type/size limits on the
  Phase 3 photo upload endpoint. A minimal check (content-type allowlist,
  max size) is cheap now and avoids an easy footgun later; doesn't need to
  be more than a few lines. Proceed
