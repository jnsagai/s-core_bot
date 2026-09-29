# Verification: F008 Quality Qualification and Release Evidence

Commands and results as actually run. Harness tests use fake providers (**mocked**) over the
F004/F005 fixture snapshot; real runs are recorded in their own sections.

## Phases 1–3 (T001–T008), 2026-09-29

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
411 files already formatted / All checks passed! / Success: no issues found in 129 source files
$ uv run pytest -q
1045 passed, 10 skipped (opt-in)
```

- JUnit parsing (`test_junit.py`): passed/failed (failure and error)/skipped per test.
- Suite model (`test_suite_files.py`, `test_freeze.py`):
  - answerable cases need facts and gold evidence;
  - `human_reviewed` needs a reviewer and a date;
  - regex patterns must compile;
  - composition rules detect a short category and a non-stratified split;
  - the freeze detects a change, and re-freezing keeps the previous hash.
- Harness (`test_harness.py`):
  - recall@10, safe handling, false abstention, citation integrity, forbidden hits and denominators;
  - only a human-reviewed held-out file is unlabelled;
  - the privacy scan catches a planted log line containing question text and finds 0 in a clean run;
  - combined runs report each run and the spread.
- Review (`test_review.py`):
  - the sheet has empty judgements and reviewer;
  - an unfilled sheet is rejected;
  - a filled sheet yields precision 1/2 and coverage 0.5 with categories;
  - a partial review counts unreviewed items;
  - a changed report, edited claim text, unknown case or unknown judgement is rejected.
- CLI (`test_cli_qualify.py`):
  - help lines;
  - a dev run writes the report and review sheet;
  - held-out is refused until frozen, `--reason` is required, and a frozen held-out run with
    `--runs 2` writes a combined report;
  - review import rejects an unfilled sheet and accepts a filled one.

### Suite authoring (T008)

- `eval/suite/dev.yaml` has 60 cases and `eval/suite/heldout.yaml` 40, agent-authored from the
  normalized text of the pinned sources (score-platform `e2373d8`, score-process `66321fe`) and
  not from this system's answers.
- Composition: 15/15/15/15 core categories, 20 unsupported, 20 adversarial; split 9/6 and 12/8 per
  category; no repeated question.
- All gold locators resolve in the active snapshot (checked by script: 0 missing).
- Every case is `review.status: unreviewed`.
- Held-out questions are all new (none from `retrieval-dev.yaml`/`answers-dev.yaml`).

```text
$ uv run score-assistant eval freeze --split heldout --reason "initial freeze before any held-out run (agent-authored, unreviewed)"
frozen eval/suite/heldout.yaml sha256 02d0cd29c78a5570… (40 cases) → eval/suite/heldout.freeze.json
```

The freeze manifest is committed before any held-out run (see git history).
