# CLI Contract: F008

All commands are offline except for loopback calls to the local runtime. Exit codes: `0` completed
(metrics are reported, not gated), `1` operational failure (runtime unavailable, freeze mismatch
for held-out), `2` usage or malformed input.

| Command | Help first line |
| --- | --- |
| `eval suite --split dev\|heldout [--runs N] [--snapshot ID]` | Runs the evaluation suite (retrieval and answers) and writes reports and review sheets; development measurement unless human-reviewed held-out. |
| `eval freeze --split heldout --reason TEXT` | Freezes a suite file by recording its hash; runs refuse a changed frozen file. |
| `eval review import --sheet FILE --report FILE` | Imports a human-filled review sheet and computes support precision and required-fact coverage. |
| `eval adversarial [--cases eval/hostile/cases.yaml]` | Runs the synthetic hostile suite with the local models on a throwaway snapshot; any failure is critical. |
| `eval performance --cases FILE [--cases FILE] [--answers N]` | Measures retrieval, progress, answer, cancellation and memory against the performance budgets. |
| `models qualify` | Records the locked models' identity, license and context from the local runtime (no downloads). |
| `release report [--gates eval/release-gates.yaml]` | Builds the release report from recorded evidence; gates without evidence are "not run", human-judged gates without a review are "blocked". |

Scripts: `scripts/offline_check.sh` (blocked-egress scenario; writes `data/reports/offline-*.json`),
`scripts/check_traceability.py` (exit 1 listing problems).

Report files (under `data/reports/`): `suite-<split>-<utc>-run<N>.json`,
`suite-<split>-<utc>-review.yaml`, `suite-<split>-<utc>-combined.json`, `human-review-<utc>.json`,
`adversarial-<utc>.json`, `offline-<utc>.json`, `performance-<utc>.json`, `models-<utc>.json`,
`pytest-<utc>.xml`, `vitest-<utc>.xml`, `release-<utc>/report.{md,json}`.
