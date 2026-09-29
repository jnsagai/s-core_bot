# Quality evidence and the release report

F008 adds commands that measure quality and assemble a release report. The report never claims
more than the evidence shows: a gate without an evidence file is `not run`, and a gate that needs a
human review is `blocked` until one is imported.

## Regenerate the evidence

```bash
C=config/local.yaml
uv run score-assistant --config $C eval suite --split dev                 # 60 development cases
uv run score-assistant --config $C eval suite --split heldout --runs 3    # 40 frozen held-out cases
uv run score-assistant --config $C eval adversarial                       # synthetic hostile suite
scripts/offline_check.sh                                                  # blocked-egress scenario (no root)
uv run score-assistant --config $C eval performance --cases eval/suite/dev.yaml --cases eval/suite/heldout.yaml
uv run score-assistant --config $C eval exact-ids
uv run score-assistant --config $C models qualify
S=$(date -u +%Y%m%dT%H%M%SZ); uv run pytest --junitxml=data/reports/pytest-$S.xml
(cd frontend && npx vitest run --reporter=junit --outputFile=../data/reports/vitest-$S.xml)
uv run score-assistant --config $C release report                         # data/reports/release-<utc>/
```

Evidence counts only if it matches the active snapshot, the locked model digest and, for held-out
gates, the current freeze. Rebuilding or activating a snapshot makes older evidence stale.

## Reviewing (the step only a person can do)

1. Open `data/reports/suite-heldout-<utc>-review.yaml` (run 1 of the held-out runs).
2. Judge every claim and every required fact following `docs/quality/review-rubric.md`, and fill
   in `reviewer` and `reviewed_on`.
3. Import the sheet:
   `uv run score-assistant --config $C eval review import --sheet <sheet> --report <run1 report>`.
4. Mark the reviewed cases in `eval/suite/*.yaml` (`review: {status: human_reviewed, reviewer, date}`).
   Held-out corrections go through `eval freeze --reason "…"`.
5. Regenerate the release report.

## The held-out freeze

`eval/suite/heldout.yaml` is frozen by `eval/suite/heldout.freeze.json`. Runs refuse a changed
file, and a test fails on a mismatch. Never tune the system on held-out results.

## Current report

`docs/quality/release-report-2026-09-29.md`: verdict **blocked**, only by items that need a person
(the suite review, the two human-judged metrics, the three held-out quality gates on unreviewed
cases, and the real-browser walkthrough). 27 gates pass; public hosting is deferred.
