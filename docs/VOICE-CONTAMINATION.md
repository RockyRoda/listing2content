# Foreign material leaking into listing copy - fixed

Status as of 2026-07-28. Two defects, both found while testing Phase 4's
voice profile (PR #9), both now fixed:

- **Voice sample facts** in the copy (a fabricated new roof, an open house
  that was not happening) - fixed by keeping the samples out of the
  generation prompt entirely. 0 / 36 runs, was ~6%.
- **Photo numbering** in shot directions - fixed by removing the numbering
  and reframing the shot directions. 0 / 52 runs, was 22%.

Both had the same shape: material that is in the prompt for one purpose gets
used for another, and no wording of a prohibition reliably stopped it -
removing the material did. Both also had the same measurement trap, below.
The history is kept because three rounds of prompt fixes looked successful
and were not.

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

## What has been tried (all superseded by the fix)

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

## The fix: the generator never sees the samples

Prompt wording was a dead end - v2 already asked for exactly the right thing
and still failed ~6% of the time, and the failure rides on caption variation
that no rewording controls. So the samples were removed from the generation
context instead.

`generation.extract_style()` distils the samples into three form-only
descriptors (`StyleProfile`: sentence rhythm, vocabulary, punctuation).
`put_voice_profile` runs it once on upload and stores the result in
`voice_profiles.style_notes`; `create_package` passes `style_notes` to
generation and never reads `sample_text`. The samples are still stored and
shown back to the agent, but nothing downstream reads them.

Cost is one extra LLM call per voice-profile upload, not per generation.

### The extractor leaked too, at first

The first version of `STYLE_PROMPT` invited short illustrative quotes ("where
it helps, quote a short phrase that is purely stylistic"). The model promptly
used a **content-bearing** quote to illustrate a structural point:

> Repetition of structure ("Roof is new. Furnace is new.") is common

That would have piped the exact fact being guarded against straight into
every generation. `STYLE_PROMPT` now forbids quoting outright and requires
patterns be described instead. **Do not re-add the quoting allowance.**

### Measurements after the fix

All with `--fresh-captions`, at the smoke test's input shape:

| Check | Result |
|---|---|
| Descriptors carrying sample facts (terse) | 0 / 20 |
| Descriptors carrying sample facts (lyrical) | 0 / 12 |
| Foreign facts in generated copy (terse) | 0 / 24 |
| Foreign facts in generated copy (lyrical) | 0 / 12 |

Voice strength improved rather than regressed, and the profiles separate
sharply - terse averages **3.4** words/sentence, lyrical **21.6**, against a
no-voice control of ~17.1. Descriptors steer harder than raw samples did
(8.6 words for terse under v2), because a stated instruction outweighs an
implied example. Worth watching that a terse profile does not become clipped
to the point of reading badly.

`scripts\verify-phase4.ps1`: 28/29, both voice checks passing.

## The photo-numbering leak (fixed 2026-07-28)

The same failure in a second form: shot directions pointed back at the source
photo list. `NUMBERING_REMINDER` had measured 0 / 40 and was believed fixed.
Re-measured properly it ran at **9 / 40 (22%)**:

> `[Soft focus on the abstract blue sculpture (photo 1) in the villa's atrium]`
> `[Close-up of the sculptural blue ribbon from the first photo]`

The old figure was wrong twice over - it froze the captions, and its regex
(`photo\s*\d`) only caught the digit form. Six of the nine real failures said
"the second photo" or "second image" and would have passed the check.

**Root cause.** The prompt asked for "brief shot directions" over a numbered
photo manifest. A shot direction's job is to tell an editor which asset to
use, and the numbering was the only vocabulary available for that, so the
model used it. Note it usually *did* describe the subject ("the sculptural
blue ribbon") and then anchored it to the source anyway - the reminder was
half-working, and no wording of it removed the pull.

**Fix**, in two parts, because removing the numbers alone was not enough:

1. The photos are no longer numbered in the prompt, and `SlideDraft` no longer
   carries `photo_number` - slides bind to photos by position. This kills
   "photo 2", which came straight off the manifest.
2. Ordinals survive without numbers, since the model can count an ordered
   list. So `ASSEMBLY_PROMPT` now frames shot directions as what the viewer
   sees "for an editor who cannot see the photo list", and `SOURCE_REMINDER`
   forbids positional reference explicitly.

Measured 0 / 52 with fresh captions (40 runs at 2 photos, 12 at 8). Slide
counts were correct in all 52, which is what makes positional binding safe;
`probe_voice.py` reports that as `wrong slide count` on every run.

## Docker (verified 2026-07-28)

Phase 4 now runs in the container: `.\scripts\start-windows.ps1` then
`.\scripts\verify-phase4.ps1` gives **29/29**, including both fixes above.
The photo-storage path arithmetic, previously checked by inspection only,
works - `slide photo_url serves the image to its owner` passes. Also
confirmed in the container: the static frontend is served, `extract_style`
runs on upload and populates `style_notes`, and it stores clean UTF-8.

One trap when checking by hand: Windows PowerShell 5.1's `Invoke-RestMethod`
mis-decodes UTF-8, so curly quotes in `style_notes` come back as mojibake on
the console. The stored bytes are fine - read them from SQLite before
concluding there is an encoding bug.

## How to resume

`scripts\verify-phase4.ps1` is the end-to-end check (29 checks, needs the app
running at :8000 and real LLM calls). `backend\probe_voice.py` is the
isolation tool:

```bash
cd backend
uv run python probe_voice.py --runs 20 --style-only          # extractor alone
uv run python probe_voice.py --runs 24 --tone "" --fresh-captions   # full path
```

`--fresh-captions` is not optional for any leak measurement - without it the
probe cannot see this class of bug at all. `--style-only` is the cheap check:
extraction is the one place the samples are read, so clean descriptors mean
no foreign fact can reach generation.

Every run reports foreign facts, photo numbering, and wrong slide counts
together, so any of the three can be measured from the same runs. Prefer
`--workers 1` at high photo counts; the vision calls fan out per photo and
the provider drops connections when too many are in flight.

Backend unit tests stay offline and green: `cd backend && uv run pytest`.
