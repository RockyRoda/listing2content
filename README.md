# Listing2Content

Content packages for luxury and resort-market real estate listings. An agent
enters a listing's specs and uploads its photos; the app reads the photos, then
drafts a carousel, a caption set, and a Reel script in the agent's own voice,
ready for a quick review-and-approve pass.

## Run it

Docker is the only prerequisite. Add your
[OpenRouter](https://openrouter.ai/keys) key first:

```bash
cp .env.example .env      # then put your OPENROUTER_API_KEY in it
```

```bash
scripts/start-mac.sh      # macOS
scripts/start-linux.sh    # Linux
.\scripts\start-windows.ps1   # Windows
```

The app comes up at <http://localhost:8000>. Sign up, add a listing with
photos, optionally upload writing samples under **Voice profile**, then
generate. Stop it with the matching `stop-*` script.

Every listing also has an **Assistant** panel. Tell it a detail
("4 beds, 4.5 baths, asking $8.95M") and it fills the fields in; ask it to
shorten a caption and it rewrites that one, leaving the rest alone.

> **All data is discarded when the app restarts** — accounts, listings, photos,
> and generated packages. That is deliberate for v1; see decision 13 in
> `docs/PLAN.md`.

To explore with data already in place, run `.\scripts\seed-demo.ps1` after
starting: it creates an agent (`demo@studio.com` / `demo1234`) with a voice
profile and four listings covering each state the package page can be in.

## How it works

One Docker image: a FastAPI backend serving a statically exported Next.js
frontend, with SQLite inside the container. The API lives under `/api`; the
frontend owns everything else.

Generation is two steps. Each photo is first described by a vision model
(`google/gemini-2.5-flash`), then those descriptions, the listing specs, and
the agent's voice profile go to `openai/gpt-oss-120b` on Cerebras, via
OpenRouter and LiteLLM, with a Pydantic response schema.

The generator never sees the agent's raw writing samples — only style
descriptors distilled from them on upload. Showing it the samples carried facts
about the agent's *other* properties into new listings;
`docs/VOICE-CONTAMINATION.md` has the measurements. The assistant writes listing
copy too, so the same rule binds it.

The assistant is one structured-output call per turn: it gets the listing as it
stands, the package copy with its row ids, and the conversation so far, and
returns a reply plus the fields to change. Its edits go through the same code
path as the manual review pass, so approving still covers the exact copy
approved — a rewrite sends the package back to draft.

## Develop

```bash
cd backend  && uv run uvicorn app.main:app --port 8000   # API (Python 3.12+)
cd frontend && npm install && npm run build              # static export
```

FastAPI serves `frontend/out` when it exists, so build the frontend once and
the whole app is at <http://localhost:8000>.

## Test

```bash
cd backend  && uv run pytest                      # 97 tests, 100% coverage of app/
cd frontend && npm run build && npm run e2e       # 14 Playwright specs
.\scripts\verify-phase8.ps1                       # proves the tests fail when the code breaks
```

Neither suite needs an API key or a running app. The browser specs need the
export built (hence `npm run build`) and, once, `npx playwright install chromium`.

`docs/TESTING.md` covers all of it, including the smoke-test scripts that make
real LLM calls, and what is deliberately not covered.

## Not in v1

- **Persistence** across restarts, and any deployment beyond a local container.
- **CI.** Tests are run by hand.
- The mac and linux scripts have been exercised on Windows through Git Bash but
  never on real macOS or Linux.

## Docs

`docs/PLAN.md` is the build plan and the record of what each phase decided.
`docs/TESTING.md`, `docs/TEST-PHASE5.md`, `docs/TEST-PHASE7.md`, and
`docs/TEST-PHASE8.md` are the test guides. MIT licensed.
