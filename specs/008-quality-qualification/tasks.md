---

description: "Task list for F008 Quality Qualification and Release Evidence"
---

# Tasks: F008 Quality Qualification and Release Evidence

**Input**: Design documents from `specs/008-quality-qualification/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md,
checklists/evidence.md

**Tests**: MANDATORY (constitution VII). Harness code is tested with fake providers and fixture
snapshots (mocked); real runs are recorded separately in `verification.md`; skipped `real_runtime`
tests are "not run".

## Format: `[ID] [P?] [Story] Description`

- **[Story]**: US1 (release report), US2 (suite + review), US3 (offline/privacy/adversarial),
  US4 (performance), US5 (traceability + models)

---

## Phase 1: Setup

- [x] T001 [P] Create `src/score_docs_assistant/qualification/` (`__init__.py` + modules per plan)
  and `cli/qualify.py` registered in `cli/main.py`

## Phase 2: Foundational

- [x] T002 [P] `qualification/junit.py`: parse pytest/vitest JUnit XML into test outcomes
  (passed/failed/skipped per test name); tests in `tests/unit/test_junit.py`
- [x] T003 [P] `qualification/suite.py`: SuiteCase/SuiteFile models, loader, composition checks
  (100, minimums, stratification, unique IDs), freeze manifest write/verify; tests in
  `tests/unit/test_suite_files.py` and `tests/unit/test_freeze.py` (with small fixture files)

**Checkpoint**: gate green; commit.

---

## Phase 3: US2 — Suite, harness, review (P1)

- [x] T004 [US2] `qualification/harness.py`: `run_suite` (retrieval top 10 + answers per case;
  metrics recall@10, status agreement, safe handling, false abstention, citation integrity,
  forbidden hits, evidence overlap, latency; labels; freeze check for held-out; log capture and
  question-text scan) and `combine_runs` (per-run metrics + spread); tests in
  `tests/unit/test_harness.py` over the F004/F005 fixture snapshot with fake providers
- [x] T005 [US2] `qualification/review.py`: review sheet generation (claim IDs, facts, citations,
  forbidden hits) and `import_review` (run reference, claim IDs, reviewer/date required, partial
  review counts, precision/coverage per category); tests in `tests/unit/test_review.py`
- [x] T006 [US2] CLI `eval suite`, `eval freeze`, `eval review import` in `cli/qualify.py`;
  contract tests in `tests/contract/test_cli_qualify.py`
- [x] T007 [US2] `docs/quality/review-rubric.md` (FR-004, with examples)
- [x] T008 [US2] Author `eval/suite/dev.yaml` (60) and `eval/suite/heldout.yaml` (40) from the
  pinned sources; `tests/unit/test_suite_files.py` validates the committed files; run
  `eval freeze --split heldout` and commit the manifest BEFORE any held-out run

**Checkpoint**: gate green; commit and push (freeze committed).

---

## Phase 4: US3 — Adversarial, offline, privacy (P1)

- [x] T009 [P] [US3] `eval/hostile/` SYNTHETIC documents and `cases.yaml` (≥ 10 cases, R5)
- [x] T010 [US3] `qualification/adversarial.py`: throwaway snapshot from `eval/hostile/` with the
  production build pipeline, answers per case, automated judges; `eval adversarial` CLI; tests
  (judges unit + fake-provider integration) in `tests/unit/test_adversarial_judges.py` and
  `tests/integration/test_adversarial_snapshot.py`
- [x] T011 [US3] `qualification/offline.py` probe + `scripts/offline_check.sh` namespace wrapper
  (egress probe, private runtime, serve, probe, report, cleanup); unit test of the probe against a
  fake HTTP app; `not run` path when `unshare` fails

**Checkpoint**: gate green; commit.

---

## Phase 5: US4 — Performance (P2)

- [x] T012 [US4] `qualification/performance.py`: warm/cold/cancellation/memory measurement,
  percentiles, budgets, insufficient-sample rule; `eval performance` CLI; tests with fake
  providers in `tests/unit/test_performance.py`

## Phase 6: US5 — Traceability and model qualification (P2)

- [x] T013 [P] [US5] `scripts/check_traceability.py` + `tests/unit/test_traceability.py` (fixture
  spec/traceability pairs and the real files); add to CI; fix any real gaps it finds in
  `docs/TRACEABILITY.md`
- [x] T014 [P] [US5] `qualification/models.py` + `models qualify` CLI (lock + `/api/show`, no pull);
  tests with a fake runtime in `tests/unit/test_model_qualification.py`

## Phase 7: US1 — Gates and release report (P1, needs the evidence producers)

- [x] T015 [US1] `qualification/gates.py` (gate file model, evaluation: report/tests/manual,
  stale evidence, development labels, human gates) and `qualification/report.py` (Markdown/JSON,
  sections, verdict); tests in `tests/unit/test_gates.py`, `tests/unit/test_release_report.py`
  covering every status path and the critical override
- [x] T016 [US1] `eval/release-gates.yaml` covering every master §13.3 threshold, §13.4 budget and
  local AT-01–AT-18 scenario; `release report` CLI; a test that every AT and threshold ID has a gate

**Checkpoint**: gate green; commit and push.

---

## Phase 8: Real runs (evidence)

- [x] T017 Run `eval suite --split dev` (real) and record it
- [x] T018 Run `eval suite --split heldout --runs 3` (real, after the freeze commit) and record it
- [x] T019 Run `eval adversarial` (real) and record it
- [x] T020 Run `scripts/offline_check.sh` (real) and record it; update A-032
- [x] T021 Run `eval performance` (real, ≥ 50 queries) and record it
- [x] T022 Run `models qualify` (real) and record it
- [x] T023 Run pytest/vitest with JUnit output and `check_traceability.py`, then `release report`;
  commit the report copy to `docs/quality/release-report-2026-09-29.md`

## Phase 9: Polish

- [x] T024 [P] Docs: README, CLAUDE.md commands, `docs/user/` quality guide (how to review and
  regenerate the report)
- [x] T025 [P] `docs/BACKLOG.md`, `docs/TRACEABILITY.md`, `docs/ASSUMPTIONS.md` (A-045 onward)
- [x] T026 Full gate; quickstart walk; `verification.md`

---

## Dependencies

Setup → Foundational → US2 (suite before held-out runs; freeze before T018) → US3/US4/US5 (independent)
→ US1 (gates read everyone's reports) → real runs → polish.
