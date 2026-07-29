# Testing Phase 5 — review / approve / edit

Phase 5 added two endpoints (`PUT /listings/{id}/package`,
`POST /listings/{id}/package/approve`) and the editable package page.

Three levels, cheapest first. Level 1 needs nothing but the repo; levels 2 and
3 need the app running and a working `OPENROUTER_API_KEY`.

---

## 1. Offline tests — no API key, no server

The LLM calls are stubbed, so this runs anywhere in a few seconds.

```powershell
cd backend
uv run pytest                                        # whole suite, 48 tests
uv run pytest tests/test_content_packages.py -v      # packages only, 19 tests
uv run pytest tests/test_content_packages.py -k "edit or approve" -v   # the 8 Phase 5 tests
```

Expect `48 passed`. The eight Phase 5 tests cover:

| Test | What it proves |
| --- | --- |
| `test_edits_persist_across_a_reload` | An edit to the script, slides, and captions survives a fresh GET |
| `test_editing_keeps_the_slides_photo_mapping` | Editing text leaves `listing_photo_id` and `order_index` alone |
| `test_approve_flips_the_status` | `status` goes `draft` -> `approved` and stays |
| `test_editing_an_approved_package_returns_it_to_draft` | Approval does not outlive the copy it approved |
| `test_editing_another_packages_row_is_rejected` | A slide id from another package 404s, and **both** packages are unchanged |
| `test_editing_before_generating_is_404` | Edit and approve both 404 when no package exists |
| `test_edit_and_approve_are_owner_scoped` | Another agent gets 404; no token gets 401 |
| `test_regenerating_replaces_an_approved_package_with_a_draft` | Regeneration hands back a draft, not a stale approval |

---

## 2. Smoke test — running app, real generation

Start the app, either way:

```powershell
.\scripts\start-windows.ps1        # Docker; reads .env for the API key
```

```powershell
# or run it locally: build the frontend once, then serve it from the backend
cd frontend; npm run build
cd ..\backend; uv run uvicorn app.main:app --port 8000
```

Then:

```powershell
.\scripts\verify-phase5.ps1
```

Expect `24 passed, 0 failed`. It seeds a package with one real generation
(~30s, uses API credit), then exercises edit, reload, approve, revert-to-draft,
regeneration, cross-package ids, and owner scoping over HTTP. It finishes by
printing a package URL and sign-in credentials — use those for step 3.

Pass `-PhotoDir C:\path\with\jpgs` if the default Windows wallpaper folder has
no `.jpg` files.

---

## 3. Manual UI pass — the part automation doesn't cover

The steps above prove the API. This proves the page. Sign in with the
credentials `verify-phase5.ps1` printed and open the package URL it printed.

| Do this | Expect |
| --- | --- |
| Look at the review bar | A grey **Draft** badge, an enabled **Save edits**, a disabled **Approve** |
| Type into a slide caption | `Unsaved edits - save before approving.` appears; **Approve** disables |
| Watch the photos while typing | They stay put — no flicker back to the loading placeholder |
| Click **Save edits** | `Saved.`; **Save edits** disables again; badge still **Draft** |
| **Reload the page (F5)** | The edited text is still there — *this is the plan's stated validation* |
| Click **Approve** | Badge turns brass **Approved**; **Approve** disables |
| Reload again | Still **Approved** |
| Edit a caption, then Save | Badge drops back to **Draft** — approval doesn't cover changed copy |
| Edit the Reel script and a caption, Save, reload | Both persisted |
| Click **Regenerate** | Fresh copy, badge **Draft**, your edits gone (regeneration replaces the package) |

Tab through the fields to confirm each textarea is reachable and labelled
(slide captions announce as "Slide N caption"; the Reel script as "Reel
script").

---

## What is deliberately not covered

- **Reordering or reassigning slide photos.** Phase 5 is a text pass; the
  photo-to-slide binding is fixed at generation. See decision 8 in
  `docs/PLAN.md`.
- **Concurrent edits from two tabs.** Last write wins. Single-agent tool, and
  the DB is wiped on restart anyway (decision 13).
- **Approving with unsaved edits.** Prevented in the UI rather than the API —
  the API will happily approve whatever is currently stored.
