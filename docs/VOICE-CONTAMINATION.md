# Open issue: voice sample facts leak into listing copy

Status as of 2026-07-28. Found while testing whether the Phase 4 voice
profile actually changes the writing (PR #9). The defect is still open, but
the probe/smoke-test contradiction that blocked it is resolved: the probe was
measuring the wrong thing. Measured leak rate is now **2/36 (~6%)**.

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

## Why the probe disagreed with the smoke test (resolved 2026-07-28)

**The probe captioned each photo once and reused that caption for every
run.** `generate_package` re-captions on every call, so the API varies the
photo description that the smoke test never held still. The probe was
resampling the assembly step against one frozen caption, which is a strictly
narrower experiment than the one the smoke test runs.

Freezing the caption suppressed the leak completely:

| Probe configuration | Leaks |
|---|---|
| Fixed caption, 2 photos / 1 photo / tone notes set | 0 / 36 |
| Fixed caption, 1 photo + no tone notes | 0 / 12 |
| Fixed caption, exact smoke-test inputs | 0 / 12 |
| **Fresh caption per run, exact smoke-test inputs** | **2 / 36** |

Both fresh-caption leaks were `"open saturday"`, matching the smoke test.
`probe_voice.py --fresh-captions` reproduces the defect; without that flag
the probe cannot see it, whatever its other settings.

Ruled out along the way, each measured at 0/12 with a fixed caption, so none
of these is the cause:

- **The queued hypothesis** - 1 photo with no tone notes, leaving the sample
  as the only voice input. Clean.
- **BOM and line endings.** The smoke test writes the sample with
  `Out-File -Encoding utf8`, which in Windows PowerShell 5.1 emits a UTF-8
  BOM and CRLF endings; `put_voice_profile` strips whitespace but not `﻿`.
  Reproduced with `--bom`. Clean.
- **Listing fields.** `Invoke-VoiceRun` omits `interior_sqft`, `mls_number`,
  and `description`. Reproduced with `--thin-listing`. Clean.
- **A different photo.** The probe's first photo is
  `Spotlight\img14.jpg`; the smoke test's is `ThemeA\img20.jpg`. Reproduced
  with `--smoke-photo`. Clean.

### What this does and does not settle

The true leak rate under v2 is about **6% (2/36)**, not zero. The earlier
"~3%" was wrong for the reason already recorded, and "0/36" was wrong because
it froze an input the real path varies.

It does not fully explain the smoke test's 2-in-3. At a 6% rate that streak
has probability ~0.01, so either it was an unlucky run or a smaller residual
difference remains. With n=3 that cannot be settled; it needs more smoke-test
runs, not more analysis. Treat ~6% as the working figure.

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
context entirely rather than asking the model to ignore them. Prompt wording
is now a poor bet: v2 already asks for exactly the right thing and still
fails 6% of the time, and the failure rides on caption variation, which no
amount of rewording controls.

Whatever is tried next, measure it with `--fresh-captions` and against the
6% baseline. A fixed-caption run cannot tell success from the masking effect
described above.

## Also still open

- **Photo-numbering leak.** A separate bug where shot directions said "from
  Photo 1". Fixed by the same placement move (`NUMBERING_REMINDER`), measured
  0 / 40 - but every one of those runs held the caption fixed, which is now
  known to hide exactly this kind of failure. That measurement should be
  redone with `--fresh-captions` before the fix is trusted.
- **Docker.** Phase 4 has never been executed in the container.
  `.\scripts\start-windows.ps1` then `.\scripts\verify-phase4.ps1`. The path
  arithmetic was verified by inspection only.

## How to resume

`scripts\verify-phase4.ps1` is the end-to-end check (29 checks, needs the app
running at :8000 and real LLM calls). Its voice section is the one that
surfaces this. `backend\probe_voice.py` is the isolation tool - reproduce with:

```bash
cd backend
uv run python probe_voice.py --runs 24 --tone "" --fresh-captions
```

Backend unit tests stay offline and green: `cd backend && uv run pytest`.
