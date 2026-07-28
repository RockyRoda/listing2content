# Open issue: voice sample facts leak into listing copy

Status as of 2026-07-27. Found while testing whether the Phase 4 voice
profile actually changes the writing (PR #9). Not resolved.

## The defect

`voice_profiles.sample_text` is the agent's past writing, which advertises
**other** properties. The assembly step copies its style, but sometimes also
copies its **facts** into the listing being marketed. Observed output:

> "...premium finishes, and a brand-new roof ensure lasting value..."
> `[End card] Text on screen: "Open Saturday, noon-3 pm."`

The test listing has no new roof and no open house. For real estate
marketing this is a false claim about a property and a fabricated event -
materially worse than a style wobble. It is the most serious open problem in
Phase 4.

## What has been tried

`_voice_brief()` in `backend/app/generation.py` builds the AGENT VOICE block.
The guard lives there rather than in `ASSEMBLY_PROMPT`, because an earlier
experiment on a separate bug established that **placement beats wording** for
this model: moving a constraint next to the text it governs worked where
rewording it in the system prompt did nothing.

| Prompt version | Foreign facts | Voice strength (terse profile) |
|---|---|---|
| No guard | 1 leak / 8 runs | 10.1 words/sentence |
| v1 - "take no facts from them" | 0 / 24 | **weakened**: 12.9 words, profiles overlap |
| v2 - current, "match closely ... take only the voice" | 0 / 36 in probes | restored: 8.6 words |

v1 showed the two goals are coupled: suppressing fact-borrowing also
suppressed style-borrowing. v2 asks for the style explicitly *and* forbids
the facts, which recovered both.

## The unresolved contradiction

v2 measures clean in the Python probe but leaks in the PowerShell smoke test:

- `backend/probe_voice.py`: **0 leaks / 36 runs**
  (24 with 2 photos + no tone notes, 12 with 1 photo + tone notes set)
- `scripts/verify-phase4.ps1` voice check: **2 leaks / 3 runs**, both
  `"open saturday"`

Two out of three against zero out of thirty-six is not sampling noise. The
probe and the smoke test differ systematically somewhere, and until that is
identified the true leak rate is unknown. An earlier estimate of "~3%" in
the PR discussion was wrong - it averaged the two populations as if they
were one.

## Leading hypothesis, and the next experiment

Every clean probe run had **either** 2 photos **or** tone notes set. The
smoke test's `Invoke-VoiceRun` uses **1 photo and no tone notes**, so the
writing sample is the only voice input and the only filler for a thin photo
brief. That exact combination has never been probed.

Run this first:

```bash
cd backend
uv run python probe_voice.py --runs 12 --photos 1 --tone ""
```

If it reproduces, the cause is confirmed: the guard weakens when the sample
is the sole voice input. If it comes back clean, the difference is in the
delivery path, not the prompt - check these next:

- **BOM and line endings.** The smoke test writes the sample with
  `Out-File -Encoding utf8`, which in Windows PowerShell 5.1 emits a UTF-8
  BOM and CRLF endings. `voice_profiles.put_voice_profile` decodes with
  `errors="ignore"` and does not strip `﻿`, so the stored text starts
  with a BOM. The probe passes a plain Python string with `\n`.
- **Listing fields.** The probe's `LISTING` includes `interior_sqft`;
  `Invoke-VoiceRun` omits `interior_sqft`, `mls_number`, and `description`,
  so the model has less real material to work with.

## Candidate fixes, once the cause is known

1. Strengthen the guard specifically when `tone_notes` is empty.
2. Stop passing raw sample text. Extract style descriptors once (sentence
   length, register, punctuation habits) and store those instead, so no
   foreign facts ever reach the assembly prompt. Structural, ends the class
   of bug, costs one extra LLM call at voice-profile upload time.
3. Validate after generation: flag copy containing figures or claims absent
   from the listing. Catches the whole family, including hallucinations that
   do not come from the sample.
4. Accept it and rely on Phase 5's human approve/edit pass. Cheapest, but
   the product's premise is a draft that is nearly ready to post.

Option 2 is the most promising - it removes the foreign facts from the
context entirely rather than asking the model to ignore them.

## Also still open

- **Photo-numbering leak.** A separate bug where shot directions said "from
  Photo 1". Fixed by the same placement move (`NUMBERING_REMINDER`), measured
  0 / 40. But that was measured under probe conditions only. It may share
  this root cause and should be re-measured at the smoke-test shape.
- **Docker.** Phase 4 has never been executed in the container.
  `.\scripts\start-windows.ps1` then `.\scripts\verify-phase4.ps1`. The path
  arithmetic was verified by inspection only.

## How to resume

`scripts\verify-phase4.ps1` is the end-to-end check (29 checks, needs the app
running at :8000 and real LLM calls). Its voice section is the one that
surfaces this. `backend\probe_voice.py` is the isolation tool. Backend unit
tests stay offline and green: `cd backend && uv run pytest`.
