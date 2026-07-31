# Testing Phase 6 — the AI chat

Phase 6 added two endpoints (`GET`/`POST /listings/{id}/chat`), a
`chat_messages` table, and the **Assistant** panel on the listing and package
pages.

Four levels, cheapest first. Levels 1 and 2 need nothing but the repo. Levels 3
and 4 need the app running and a working `OPENROUTER_API_KEY`.

---

## 1. Offline backend tests — no API key, no server, ~10s

The LLM is stubbed at litellm's `completion`, so the real prompt building and
real structured-output parsing run.

```powershell
cd backend
uv run pytest                                   # whole suite, 97 tests
uv run pytest tests/test_chat.py -v             # the chat only, 24 tests
uv run pytest --cov=app --cov-report=term-missing
```

Expect `97 passed` and **100% statement coverage** of `backend/app`.

The 24 chat tests, grouped as they are in the file:

| Test | What it proves |
| --- | --- |
| `test_chat_starts_empty` | A new listing has no transcript |
| `test_a_turn_records_both_sides_in_order` | The agent's message and the reply are both stored, in order |
| `test_the_transcript_survives_a_reload` | A fresh `GET` returns the whole conversation |
| `test_earlier_turns_are_replayed_to_the_model` | History reaches the prompt — without it "make that shorter" has no referent |
| `test_history_is_capped` | A long session cannot grow the prompt without limit |
| `test_chat_fills_in_listing_fields` | Fields named in conversation are written and persist |
| `test_untouched_fields_are_left_alone` | `null` means "leave alone", not "clear" |
| `test_a_turn_that_changes_nothing_reports_nothing` | Both change flags are false when nothing happened |
| `test_the_prompt_names_the_fields_still_missing` | Unset fields show as `(not set)`, so chat can ask for them |
| `test_chat_edits_a_caption` | A named caption is rewritten and persists |
| `test_chat_edits_a_slide_and_the_reel_script` | Slide and script edits land; the *other* slide is untouched |
| `test_an_untouched_reel_script_is_kept` | A null script does not blank the column on a slide-only edit |
| `test_the_prompt_carries_the_current_copy_and_its_row_ids` | The model can only address rows it was given ids for |
| `test_copy_edits_are_refused_before_a_package_exists` | A rewrite with no package returns 200 and writes nothing |
| `test_the_prompt_says_when_there_is_nothing_to_edit` | The no-package text forbids drafting copy |
| `test_the_prompt_says_earlier_edits_are_already_saved` | `EDIT_REMINDER` is present — see the defect table below |
| `test_a_copy_edit_returns_an_approved_package_to_draft` | The Phase 5 rule, inherited |
| `test_talking_about_the_listing_leaves_an_approved_package_approved` | Only a copy rewrite un-approves; a spec must not |
| `test_a_row_id_from_another_package_is_rejected` | A cross-package id 404s and **both** packages are unchanged |
| `test_chat_writes_with_the_style_notes_and_never_the_samples` | The contamination invariant binds chat too |
| `test_a_provider_failure_is_a_502_and_records_nothing` | A failed turn stores no messages |
| `test_another_agent_cannot_read_or_join_the_conversation` | Owner scoping on both verbs |
| `test_chat_needs_a_token` | 401 without one |
| `test_chat_routes_through_cerebras` | Model and provider match `docs/PLAN.md` |

### Prove the tests can actually fail

Two of these could pass vacuously, so they were mutation-checked. Reproduce
either — each should turn the named test red, and **revert it afterwards**.

**The contamination guard.** In `backend/app/chat.py`, make the voice query read
the raw samples instead of the descriptors:

```python
"SELECT sample_text AS style_notes, tone_notes FROM voice_profiles WHERE user_id = ?",
```

```powershell
uv run pytest tests/test_chat.py -k style_notes
```

Expect a failure showing the sample's text (`Roof is new. Open Saturday.`) inside
the prompt.

**The no-package guard.** In `post_chat`, drop the `if current is not None`
guard so package edits are attempted with no package. Expect
`test_copy_edits_are_refused_before_a_package_exists` to fail on a 404.

---

## 2. Offline browser tests — no API key, ~7s

```powershell
cd frontend
npm run build          # the backend serves this export
npm run e2e            # 14 specs
npx playwright test e2e/chat.spec.ts    # the 7 chat specs only
```

First run only: `npx playwright install chromium`.

| Spec | What it proves |
| --- | --- |
| `opens empty, with nothing to send` | Empty state; **Send** disabled |
| `a turn shows both sides of the conversation` | Both messages render; the POST body is right; the box clears |
| `the transcript survives a reload` | The panel loads history from the server, not React state |
| `a rewritten caption replaces the copy in the editor` | **The one that matters** — see below |
| `a recorded spec appears in the listing form` | A chat-filled field shows up without a manual refresh |
| `a turn that changes nothing leaves the page alone` | A half-typed field is not refetched over |
| `a failed turn says so and keeps the message` | The error shows and the agent needn't retype |

### Prove the remount test can fail

`PackageEditor` owns its state from mount, so refetching the package after a
chat rewrite is **not** enough on its own. In
`frontend/app/listings/package/page.tsx`, change:

```tsx
key={`${pkg.id}-${rewrites}`}   ->   key={pkg.id}
```

```powershell
npm run build
npx playwright test e2e/chat.spec.ts -g "rewritten caption"
```

Expect:

```
Expected: "Mornings are slow here."
Received: "Mornings here are unhurried."
```

That is the agent reading stale copy while the server holds the new text.
**Revert the key afterwards.**

---

## 3. Smoke test — running app, real LLM calls

Start the app, either way:

```powershell
.\scripts\start-windows.ps1        # Docker; reads .env for the API key
```

```powershell
# or locally: build the frontend once, then serve it from the backend
cd frontend; npm run build
cd ..\backend; uv run uvicorn app.main:app --port 8000
```

Then:

```powershell
.\scripts\verify-phase6.ps1
```

Expect `29 passed, 0 failed`. Verified against both local uvicorn and the
container. It prints every exchange, so a failure can be read rather than
guessed at:

```
    >  It's in Wailea, Maui - 4 beds, 4.5 baths, asking 8950000.
    <  Recorded location, beds, baths, and price for the listing.
  PASS  chat recorded the beds
```

It covers, in order: an empty transcript, four fields filled from one sentence,
a question that writes nothing, a follow-up resolved against history, a copy
edit refused before a package exists, one real generation, a named caption
rewritten while the script/slides/labels/photo-bindings stay put, a spec that
leaves an approved package approved, a rewrite that returns it to draft, and
owner scoping.

Pass `-PhotoDir C:\path\with\jpgs` if the default Windows wallpaper folder has
no `.jpg` files. It costs roughly a dozen chat calls plus one generation (~60s).

### The one flaky check

`a copy rewrite returns it to draft` **missed once in three runs** — the model
occasionally answers a rewrite request without emitting the edit. Re-run before
treating it as a regression. Everything in levels 1 and 2 is deterministic.

### If generation fails

The script stops as soon as it sees that, printing the status. A 502 means the
LLM call failed; the backend log holds the exception. For Docker, confirm the
key arrived with
`docker exec listing2content printenv OPENROUTER_API_KEY`.

---

## 4. Manual UI pass

Sign in with the credentials `verify-phase6.ps1` printed, and open the package
URL it printed. The **Assistant** panel is at the bottom of both that page and
the listing edit page.

| Do this | Expect |
| --- | --- |
| Open a listing's edit page, scroll to **Assistant** | The conversation from step 3 is there — it is stored per listing, not per page |
| Type `The lot is 0.75 acres.` and Send | `Thinking...` appears, then a reply; the **Lot size** field fills in without a refresh; the status line says the assistant updated the listing |
| Type a detail into the form but **don't save**, then ask the assistant a question | Your half-typed text stays — a turn that changes nothing must not refetch over it |
| Go to the package page, ask `Make the lifestyle hook caption shorter.` | The caption text below changes in place; status says the assistant rewrote copy |
| Check the badge after that | **Draft** — a rewrite un-approves, same as a manual edit |
| Ask `What's the MLS number?` | It asks you for it rather than inventing one; nothing changes |
| Answer with just `W-448201` | It resolves the follow-up against history and fills the field |
| Reload the page (F5) | The whole conversation is still there |
| Sign out, sign up as a second agent | That agent sees none of the first agent's listings or conversations |
| Press Enter in the message box | Sends (it is a form submit) |
| Tab to the box | Announces as "Message the assistant"; the log announces as "Conversation" |

### Before a package exists

On a listing you have **not** generated for, ask `Rewrite the reel script.`
It should tell you to generate the package first, and nothing should be created.

Occasionally it will instead reply as though it did the work — measured at
2 of 6 before a prompt fix, 0 of 8 after, but **one still slipped through a
later smoke run**. Nothing is written when this happens; the reply is simply
wrong. If you see it, that is a known residual, not a new bug.

---

## What is deliberately not covered

- **Generating a package from chat.** Out of scope by decision — generation
  stays an explicit button, not something a sentence can trigger. Photos and the
  voice profile are likewise not chat-editable.
- **How well the model understands vague input.** Every offline test fixes what
  the model replies, so they check what the endpoint does with an answer, not
  whether the answer was good. `verify-phase6.ps1` uses unambiguous phrasing;
  rambling or self-contradictory instructions are untested.
- **Concurrent chat from two tabs.** Last write wins, as with the Phase 5
  editor.
- **A long conversation.** History is capped at 20 messages
  (`MAX_CHAT_HISTORY`); the cap is unit-tested, but nobody has held a
  hundred-turn conversation to see how it reads once older turns fall off.
- **Unsaved manual edits when chat rewrites copy.** The editor remounts with the
  server's text, so anything typed-but-unsaved in it is lost. Acceptable — the
  assistant just changed the copy underneath you, and showing stale local text
  would be worse.
