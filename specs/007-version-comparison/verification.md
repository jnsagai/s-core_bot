# Verification: F007 Explicit Snapshot Comparison

Commands and results as actually run. Tests with fake providers are labelled **mocked**; they
use two SYNTHETIC fixture snapshots (`tests/helpers/comparison_fixtures.py`).

## Phases 1–5 (T001–T021), 2026-09-29

### Gate

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
383 files already formatted / All checks passed! / Success: no issues found in 122 source files
$ uv run pytest -q
1005 passed, 9 skipped (opt-in markers, not run)
```

### What the new tests show (mocked)

- **Domain invariants** (`test_comparison_domain.py`): difference type/evidence/coverage rules;
  a result with a citation from the other side, an envelope bound to the wrong snapshot, the same
  snapshot twice, or an unresolved difference ID cannot be constructed. The request has no
  `history` field.
- **Metadata** (`test_comparison_metadata.py`): `different` / `right_only` / `left_only` relations,
  the identical-revisions warning, unverified and failed sources flagged, processing differences,
  `release_label` always null; coverage reasons `source_absent` / `source_failed` /
  `source_partial`.
- **Validation** (`test_comparison_validate.py`): every code from contracts/comparison-schema.md,
  12 removal/addition wording variants rejected, 4 neutral sentences accepted.
- **Prompt** (`test_comparison_prompt.py`): L/R namespacing, escaping (a breakout attempt stays
  inside its block), cited-first ordering, split budget with a reduction warning, unused budget
  moving to the other side.
- **Records** (`test_comparison_records.py`): unchanged, changed (title, text), right-only, a
  location-only change not counted, record without excerpt → `not_established`.
- **Service** (`test_comparison_service.py`): changed, unchanged and conflicting topics; repair
  success; repair failure → deterministic differences only with a warning; a "was removed" draft
  twice → no model difference and zero deletion wording in the result; one-sided model difference
  gets the server reason `source_absent`; a side without evidence skips the comparison call; exact
  records for four IDs; extractive fallback on a side; keyword degradation reported per side;
  validation, 404, `GENERATION_UNAVAILABLE` before any call, deadline 504; `answer_in_slot` runs
  while the only slot is held; immutable links for the left revision come from the archived lock.
- **Isolation** (`test_comparison_isolation.py`): 0 cross-side citations over 5 questions;
  activating the left snapshot mid-comparison changes nothing, both snapshots are pinned during
  the request (the right cannot be taken for deletion), and both pins are released afterwards.
  Finding: chunk IDs are content hashes shared by unchanged text across snapshots, so isolation is
  checked by each citation's snapshot ID, never by chunk ID.
- **HTTP** (`test_compare_api.py`): JSON result; SSE order with sides, `comparing` last, no claim
  text before the `comparison` event; error event; 422 for `history`, unknown fields, the same
  snapshot, a bad ID, a long question; 404; 503; 504; cross-site 403 on both routes; no question or
  answer text in logs; diff endpoint without any model call and its 422/404 cases; 429 while chat
  holds the slot with no waiting room; disconnect (JSON and SSE) cancels generation within 3 s and
  releases the slot and both pins; readiness `compare` available and the new capabilities limit.
- **CLI** (`test_cli_compare.py`): help lines, text and JSON output, exit codes 2/1, `snapshots
  diff` text/JSON without a model call.
- **Refactor safety**: the whole F005 suite (`answer_in_slot` split) and sync suite (lock archive)
  still pass.

## Phase 7 — Benchmark (T026–T029), 2026-09-29

### Baseline snapshot (T027, real network for sync only)

```text
$ curl -s "https://api.github.com/repos/eclipse-score/<repo>/commits?sha=main&until=2026-06-01T00:00:00Z&per_page=1"
score                ba13d8296dd6021067bdeb6ba644b0546f8ad0c6  2026-05-29T12:11:19Z
process_description  82bca166065990e52b871de47c87668b6a3d5f49  2026-05-29T13:08:17Z
$ cp -p data/source-lock.json data/source-lock.main.json        # sha256 f5c6a38f…
$ uv run score-assistant --config config/local.yaml sources sync --config config/sources-baseline.yaml
score-platform: extracted 409 files; score-process: extracted 300 files; Wrote data/source-lock.json
$ mv data/source-lock.json data/source-lock-baseline.json; cp -p data/source-lock.main.json data/source-lock.json
  → restored lock sha256 f5c6a38f… (unchanged); both locks archived in data/source-locks/
$ uv run score-assistant --config config/local.yaml index build --source-lock data/source-lock-baseline.json
embedded 6084 rows (reused 2644; 3364 unique inputs sent to the runtime)
published 20260929T075830Z-9135a190 (validated)        real 0m31.2s
$ uv run score-assistant --config config/local.yaml snapshots list
  20260929T075830Z-9135a190 validated (baseline, not activated); * 20260928T140548Z-7c6a05b3 active (unchanged)
$ uv run score-assistant --config config/local.yaml snapshots diff 20260929T075830Z-9135a190 20260928T140548Z-7c6a05b3
  score-platform different ba13d82→e2373d8 (pinned); score-process different 82bca16→66321fe (pinned);
  both needs exports right only (unverified); "No release label"; 4 warnings     (0.5 s, no model)
```

Source differences found while authoring cases: in score-process, 1 file only in the left, 15 only in the right,
271 changed (almost every need gained a `:version: 1` option), 30 unchanged; in score-platform, 147 only in the left
(module docs moved), 57 only in the right, 189 changed, 75 unchanged.

### Real findings that changed the design (A-043)

1. First real comparison: `JSON_INVALID` twice — the model copied whole excerpts into statements and the output
   was cut at 900 tokens. Fix: 600-character statements, "describe, don't copy" rule, schema maxLength one above
   the limit so a grammar cut-off is rejected (never shown truncated). Re-run: valid output (455 output tokens).
2. The model then wrote "Right evidence adds …" (an absence claim about the left). Fix: forbidden wording widened
   (adds/added/introduces), a neutral-wording hint in the repair message, and salvage of individually valid
   differences after the repair. Re-run: repaired output fully valid.

### Benchmark (T028; development measurement — agent-authored cases, unreviewed)

`eval/comparison-dev.yaml`: 12 cases (4 changed, 3 unchanged, 3 missing coverage, 2 exact ID).

| Run | Type agreement | Isolation violations | Citation integrity | Deletion claims | Deterministic only | p50 / p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 (`comparison-20260929T081055Z.json`) | 9/12 | 0 | 12/12 | 0 | 1 | 17.8 s / 25.2 s |
| 2, after generic per-code repair hints (`comparison-20260929T081504Z.json`) | 10/12 | 0 | 12/12 | 0 | 0 | 16.7 s / 27.7 s |

Run 1 misses: cmp-02 (`CHANGED_WITHOUT_DIFFERENCE` twice → deterministic only), cmp-04 (typed `unchanged`; the
changed excerpts were dropped by the budget warning), cmp-09 (one-sided `changed` differences dropped by
validation). Run 2 misses: cmp-04 (same), cmp-10 (the model typed "left states X; the right evidence does not
mention X" as `changed` — honest wording without a deletion claim, but the type should be `not_established`).
Between runs only generic repair hints per validation code were added (tuning on this development set, disclosed
here). Results vary between runs of the same model (cmp-10 passed in run 1).

### Real-runtime test and timing (T029)

```text
$ SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -q tests/integration/test_real_runtime.py -k comparison -s
REAL model [('changed','model'), ('conflicting','model'), ('not_established','model')] [comparison_differences_dropped: 1 … (MISSING_SIDE_EVIDENCE)]
1 passed
```

SC-006 (warm comparison ≤ 3 × a warm single answer), question "How is the documentation published to GitHub
Pages?", baseline vs active, measured twice each:

| | run 1 | run 2 | internal timings |
| --- | --- | --- | --- |
| `ask` (active) | 4.07 s wall | 6.11 s wall | total 3 135 ms (retrieval 74, generation 2 982) |
| `compare` | 11.52 s wall | 12.89 s wall | total 10 843 / 12 160 ms (left 3 066 / 2 969, right 5 163 / 2 903, comparison 2 609 / 6 284) |

**SC-006 not met** under its strict reading: 10.8–12.2 s against a 3.1 s single answer is 3.5–3.9 ×. A
comparison is structurally two answers plus a third, longer model call; the 3 × target was set before measuring.
Recorded as open item A-044 for the owner (keep the target and optimize, or accept ~4 ×).
