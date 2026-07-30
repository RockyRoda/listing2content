# Testing Phase 8 — testing & hardening

Phase 8's deliverable *is* tests, so verifying it means two different things:
that the suites pass, and that they would fail if the code broke. Level 4 is the
one that actually proves Phase 8 did its job.

Levels 1–4 need no API key, no Docker, and no running app.

---

## 1. The backend suite — offline, ~12s

```powershell
cd backend
uv run pytest
```

Expect **`73 passed`** (48 before Phase 8).

```powershell
uv run pytest tests/test_generation.py -v        # 19, the module that had none
uv run pytest tests/test_integration_flow.py -v  # 3, the whole-product flow
```

---

## 2. Coverage — offline, ~13s

```powershell
cd backend
uv run pytest --cov=app --cov-report=term-missing
```

Expect **`TOTAL ... 100%`** across `backend/app`. `app/generation.py` went from
no direct tests at all to 100%.

---

## 3. Browser specs — offline, ~8s

```powershell
cd frontend
npx playwright install chromium   # first run only, ~115 MB
npm run build                     # the backend serves this export
npm run e2e
```

Expect **`7 passed`**. Every `/api/**` call is mocked in the browser, so no key,
LLM, or database is involved. The backend runs on port 8123 purely as the static
file server, so this does not disturb anything on 8000.

---

## 4. Do the tests actually bite? — the important one

A green suite proves nothing by itself; a test that cannot fail passes too. This
script breaks the code in six known ways and checks that the tests we claim
cover each behaviour **do** fail, then reverts every change with
`git checkout --`.

```powershell
.\scripts\verify-phase8.ps1                  # 10 passed
.\scripts\verify-phase8.ps1 -IncludeBrowser  # 12 passed (rebuilds the export twice)
```

It refuses to run if `backend/` or `frontend/` has uncommitted changes, since it
reverts with git and would discard your work.

| Mutation | Should be caught by |
| --- | --- |
| Captions attached to the wrong photos (`descriptions` reversed) | `test_generation.py` ordering test |
| Raw voice samples passed where the distillation belongs | `test_integration_flow.py` + `test_voice_profiles.py` |
| The empty-photo crash reintroduced (`if capped:` → `if True:`) | `test_generation.py` |
| Cross-package caption writes (scoping clause dropped) | `test_content_packages.py` |
| Approval surviving an edit (`status = 'draft'` dropped) | `test_content_packages.py` |
| The 8-photo captioning cap removed | `test_generation.py` |
| Photo URLs refetched on every keystroke (memo dependency swapped) | `package-review.spec.ts` |

The first row is why Phase 8 exists: **before it, reversing the caption list
left all 48 tests green.** Every slide could have carried the wrong photo's
caption and nothing would have failed.

The last two checks confirm the script cleaned up after itself — the suite is
green again and `git status` is clear.

---

## 5. The interface, with everything already set up

Phase 8 added no UI, but the browser specs assert specific on-screen behaviour,
and you may want to confirm it by eye. This seeds an agent with a voice profile
and four listings, one for each state the package page can be in.

```powershell
.\scripts\start-windows.ps1     # if it is not already running
.\scripts\seed-demo.ps1         # ~60s: two real generations
```

Then sign in at **http://localhost:8000**

- **email:** `demo@studio.com`
- **password:** `demo1234`

| Listing | Photos | Package | Try this |
| --- | --- | --- | --- |
| Oceanfront Villa Kai | 3 | `draft` | Edit a caption, **Save**, reload — it should persist |
| Hillside Hale | 2 | `approved` | Opens with a brass **Approved** badge. Edit it and Save — the badge should drop back to **Draft** |
| Sunset Ridge Estate | 2 | none | Click **Generate package** (real LLM, ~30s) |
| Bare Lot at Kapalua | 0 | none | **Generate** → expect "Add at least one photo to this listing first." |

Also worth a look: **http://localhost:8000/settings** shows the uploaded voice
samples *and* the distilled descriptors under "Your voice, as we read it" — the
samples themselves never reach the generator.

What the browser specs assert, if you want to check by eye on the villa:

| State | Expect |
| --- | --- |
| On load | Grey **Draft** badge, **Save edits disabled** (nothing typed yet), **Approve enabled** |
| After typing | `Unsaved edits - save before approving.`; Save enables, Approve disables |
| While typing | The slide photos do not flicker or reload |
| After Save | `Saved.`, Save disabled again, badge still **Draft** |

Note the first row: an earlier version of `docs/TEST-PHASE5.md` had those two
button states backwards. On load there is nothing to save, so **Save is the
disabled one**.

The database is wiped whenever the app restarts, so re-run `seed-demo.ps1` after
each start. Pass `-SkipGeneration` to seed without spending API credit, leaving
all four listings package-free.

---

## What Phase 8 does not cover

- **No CI.** Everything is run by hand; there are no GitHub Actions workflows.
- **The mac and linux scripts** still have never run on real macOS or Linux.
- **AI output quality** is only checked structurally — that a package parses,
  has slides, and does not leak the voice sample's facts. Whether the copy reads
  well is a human judgement.
- **Frontend pages other than the package editor** — sign-in, listing form,
  settings — have no browser tests.
- **Mutation coverage is a fixed list of six**, not an exhaustive tool like
  `mutmut`. It demonstrates the tests bite where it matters; it does not prove
  every line is meaningfully asserted.
