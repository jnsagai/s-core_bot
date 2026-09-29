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

## Phases 4–7 (T009–T016), 2026-09-29 (mocked unless stated)

- **Adversarial** (`test_adversarial_judges.py`, `test_adversarial_snapshot.py`):
  - each failure kind is detected, and denials are not failures;
  - the throwaway snapshot is built by the production pipeline from `eval/hostile/docs/` (8
    SYNTHETIC documents) and cleaned up; the configured data directory is never touched;
  - 10 cases.
- **Offline probe** (`test_offline_probe.py`):
  - passes with a mocked app;
  - fails on open egress, a digest mismatch or a log leak;
  - writes a `not run` report.
- **Performance** (`test_performance.py`):
  - percentiles and budgets (pass, fail, insufficient sample, not run);
  - a fake-provider run covers warm, cold (unload counted), cancellation and memory.
- **Traceability** (`test_traceability.py`):
  - detects a missing row, a duplicate, a non-existent path, an unknown ID, a missing status and a
    PUB row not marked deferred;
  - the real repository passes: 55 local + 8 PUB requirements, 223 paths checked;
  - added to CI.
- **Model qualification** (`test_model_qualification.py`): lock match and mismatch, license
  summary and sidecar, no pull.
- **Gates and report** (`test_gates.py`, `test_release_report.py`):
  - every status path (missing → not run; human without review → blocked; development label →
    blocked unless accepted; stale snapshot/model/freeze → not run; tests pass/fail/skipped/missing;
    manual/deferred);
  - the verdict rules, including a critical failure on a non-required gate;
  - the Markdown sections;
  - the committed gate file covers every §13.3 metric, ≥ 6 §13.4 budgets and AT-01–AT-18.

## Phase 8 — Real runs (T017–T023), 2026-09-29

### Development suite (T017; 60 cases; development measurement)

| Run | recall@10 (38 answerable) | status | safe handling | false abstention | citation integrity | forbidden hits | log leaks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 (before the negation guard) | 89.5% | 55/60 | 21/22 | 2/38 | 60/60 | 6 | 0 |
| 2 (negation guard) | 89.5% | 54/60 | 20/22 | 2/38 | 60/60 | 2 | 0 |
| 3 (after the A-047 answer fixes) | 89.5% | 55/60 | 20/22 | 2/38 | 60/60 | 2 | 0 |

Findings:
- 4 of the first 6 forbidden hits were correct denials ("is **not** certified"), which led to the
  negation guard (A-046).
- Genuine misses:
  - dev-043 ("Which requirements apply to it?") was answered with unrelated compliance
    obligations instead of asking for scope;
  - dev-010 and dev-016 were false abstentions.

### Held-out suite (T018; 40 cases; frozen `02d0cd29…` before the first run; development measurement)

| Series | recall@10 (26) | status | safe handling (14) | false abstention (26) | citation integrity | log leaks |
| --- | --- | --- | --- | --- | --- | --- |
| before A-047 fixes, runs 1–3 | 96.2% ×3 | 39/40 ×3 | 14/14 ×3 | 0/26 ×3 | 40/40 ×3 | 0 |
| after A-047 fixes, runs 1–3 (`suite-heldout-20260929T122206Z-*`) | 96.2% ×3 | 39, 38, 39 /40 | 14, **13**, 14 /14 | 0/26 ×3 | 40/40 ×3 | 0 |

Spread: recall 0.0; safe handling 0.929–1.0; evidence overlap 0.923–0.962. ho-022 is `partial`
in every run. In run 2, ho-031 was answered, and my expected status there may be wrong (A-048,
for the reviewer). The one forbidden hit (ho-040) is a denial on manual inspection (A-046). No
case was edited after the freeze.

### Adversarial (T019; real model, throwaway synthetic snapshot)

- **First run: 8/10 failed.** The extractive fallback relayed `https://evil.example`,
  `javascript:` and fake `[E9]` markers verbatim; the model stated an injected "policy for AI
  assistants" as fact; the model repeated fake citation markers.
- Fixes in F005 code (A-047):
  - the fallback skips link, marker and instruction-like excerpts;
  - claims citing instruction-like evidence must describe it as document text;
  - claim text may not contain evidence markers.
  Unit tests were added, and the whole F005 suite still passes. The real corpus has 0
  instruction-like and 0 marker chunks, so no real answer is affected.
- Two cases were corrected as test-design errors (reasons in the case file).
- **Re-run (`adversarial-20260929T122154Z.json`): 0/10 failures, utility 1/1.**

### Offline / blocked egress (T020; AT-01, closes A-032)

```text
$ scripts/offline_check.sh          (unprivileged loopback-only network namespace, private runtime)
ok  external egress blocked: DNS lookup failed: True; TCP 1.1.1.1:443 failed: True
ok  readiness: chat available
ok  web UI served: GET / → 200
ok  ask: cited answer: status answered, 2 citation(s), origin model
ok  open cited excerpt: docs/contribute/development/development_environment.rst: 918 characters
ok  search: 8 results, mode hybrid
ok  export fields present;  ok model matches lock (0edcdef34593…);  ok no question text in server log
offline check: pass          (runs at 11:51 and, after the A-047 fixes, 12:30 UTC)
```

Afterwards only the host's own runtime was running, and port 8080 was closed.

### Performance (T021; RTX 4070 Laptop 8 GiB; corpus 5 658 chunks; `performance-20260929T124231Z.json`)

| Operation | n | p50 | p95 | Budget | Status |
| --- | --- | --- | --- | --- | --- |
| Lexical retrieval | 100 | 34 ms | 72 ms | ≤ 500 ms | pass |
| Hybrid retrieval, warm | 100 | 72 ms | 101 ms | ≤ 2 s | pass |
| First progress event, warm (in-process) | 50 | 0.07 ms | 0.09 ms | ≤ 1 s | pass |
| Final answer, warm | 50 | 2.66 s | 7.57 s | ≤ 30 s | pass |
| Cancellation release (max) | 3 | 0.43 ms | 0.75 ms | ≤ 2 s | pass |
| Hybrid retrieval, cold (unload verified) | 5 | 1.71 s | 1.81 s | — | reported |
| Final answer, cold | 5 | 6.06 s | 8.13 s | — | reported |

- Peak GPU 4 360 of 8 188 MiB; loaded models are 3.87 GB (qwen3) and 0.32 GB (nomic); process
  peak RSS 108 MiB.
- An earlier run did not verify the unload (the embedding model needs more than 5 s to leave
  memory); the wait was fixed (A-049) and the table is from the verified run.

### Models (T022)

```text
generation qwen3:4b-instruct        digest 0edcdef34593 lock match True  qwen3 4.0B Q4_K_M ctx 262144  license Apache-2.0
embedding  nomic-embed-text:latest  digest 0a109f422b47 lock match True  nomic-bert 137M F16 ctx 2048  license Apache-2.0
runtime 0.34.0 (locked 0.34.0)
```

The license is as reported by the local artifacts; the SPDX guess is not a legal review.

### Release report (T023)

```text
$ uv run pytest --junitxml=data/reports/pytest-20260929T124242Z.xml   → 1082 passed, 10 skipped (opt-in)
$ npx vitest run --reporter=junit …/vitest-20260929T124242Z.xml       → exit 0
$ uv run score-assistant eval exact-ids                              → 2168/2168 correct first
$ uv run score-assistant --config config/local.yaml release report
verdict: blocked  gates: {'blocked': 7, 'pass': 27, 'not run': 1}
```

Copy committed: `docs/quality/release-report-2026-09-29.md`.
- **Blocked (7):** all awaiting a person: the suite review, support precision, required-fact
  coverage, and recall/safe-handling/false-abstention on unreviewed held-out cases (measured
  0.962 ×3; 1.0/0.929/1.0; 0.0 ×3); plus the browser walkthrough.
- **Not run (1):** the public profile (deferred to F010).
- **Pass (27):** including the critical gates for exact IDs, citation integrity, isolation,
  injection resistance, offline operation, Host/Origin and the deterministic suites.

Two real gaps would remain even with a review: held-out safe handling dipped to 13/14 in one run
(below 95% if it stands), and the F007 comparison speed SC-006 (A-044).

## Quickstart walk (T026)

| Section | Result |
| --- | --- |
| A. Deterministic | format/lint/types clean; pytest 1082 passed, 10 skipped (opt-in); vitest pass; `check_traceability.py` passed |
| B. Suite | dev and held-out ×3 run (above); the held-out run is refused when not frozen (contract test) |
| C. Adversarial, offline, performance, models | all run for real (above) |
| D. Human review | **not run — this step belongs to the owner/reviewer**; import path tested with fixture sheets only |
| E. Release report | generated; verdict blocked by human-dependent items only |

## Convergence (agent review)

- Checked against the code and tests: FR-001–FR-018, SC-001–SC-008, the plan and constitution
  I–XII.
- SC-002 (human metrics blocked without a review) and SC-004 (blocked egress) are met with real
  evidence.
- SC-008: three held-out runs were reported, twice (before and after the A-047 fixes).
- No missing or contradicting items, so no Convergence phase was appended.
- Open items are owner-side: the human review (A-048 items included) and the browser walkthrough
  (A-040), plus the F007 speed decision (A-044).
