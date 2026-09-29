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
