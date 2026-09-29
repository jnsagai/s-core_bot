# CLI Contract: `compare`, `snapshots diff`, `eval comparison` (F007)

Exit codes as F005: `0` a result was produced, `1` operational failure (generation unavailable,
deadline, snapshot not found), `2` usage error (including the same snapshot twice), `130`
interrupted. Nothing is downloaded; network use is loopback to the local runtime only.

## `compare "QUESTION" --left ID --right ID [--json] [--show-evidence]`

Help first line: **"Compares how two snapshots answer a question with the local model; evidence
stays separate per snapshot (no downloads)."**

```text
left  20260929T101500Z-1a2b3c4d   right 20260928T140548Z-7c6a05b3   model qwen3:4b-instruct (0edcdef34593)
sources:
  score-platform   different  3f2a91c… (pinned) → e2373d8… (pinned)
  score-process    different  12ab34c… (pinned) → 66321fe… (pinned)
  score-platform-needs  right only  — → 0cb3df7… (unverified)
No release label: per-source revisions identify each snapshot.
LEFT (status partial)
- … [L1]
RIGHT (status answered)
- … [R1]
differences:
- changed: … [L1] [R2]
- not established (right only; source absent in left): … [R3]
evidence:
[L1] score-process  process/…/inspection.rst:10-30
[R2] score-process  process/…/inspection.rst:12-41  https://github.com/…#L12-L41
```

`--show-evidence` also prints the excerpts. `--json` prints the `ComparisonResult`.

## `snapshots diff LEFT RIGHT [--json]`

Help first line: **"Shows per-source revisions and processing differences of two snapshots
(offline, no model)."** Exit 0 when the diff is printed.

## `eval comparison --cases FILE [--left ID] [--right ID] [--json]`

Help first line: **"Runs comparison cases against the local model and reports difference types,
evidence isolation and deletion claims; development measurement unless reviewed."** It writes
`data/reports/comparison-<utc>.json`. Exit 0 when the run completes, 1 when generation is
unavailable, 2 for a malformed case file.
