---

description: "Task list for F007 Explicit Snapshot Comparison"
---

# Tasks: F007 Explicit Snapshot Comparison

**Input**: Design documents from `specs/007-version-comparison/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md,
checklists/comparison.md

**Tests**: MANDATORY (constitution VII). Write tests first. Deterministic tests use
`FakeGenerationProvider`/`FakeEmbeddingProvider` (mocked) and fixture snapshots labelled
`SYNTHETIC — not S-CORE guidance`; `real_runtime` tests count as "not run" when skipped.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on incomplete tasks)
- **[Story]**: US1 (compare answers), US2 (missing coverage), US3 (metadata), US4 (UI/export),
  US5 (benchmark)
- Paths are repository-relative (package root `src/score_docs_assistant/`)

---

## Phase 1: Setup

- [x] T001 [P] Create `src/score_docs_assistant/comparison/` (`__init__.py`, docstring-only
  `metadata.py`, `records.py`, `coverage.py`, `policy.py`, `prompt.py`, `validate.py`,
  `service.py`, `evaluation.py`), `domain/comparison.py`, `api/compare_routes.py`, `cli/compare.py`
- [x] T002 [P] Add `ComparisonConfig` (`deadline_seconds` 240, `evidence_items_per_side` 5,
  `max_differences` 8) as `AppConfig.comparison` in `config/schema.py`, with a unit test of
  defaults, bounds and `extra="forbid"` in `tests/unit/test_comparison_config.py`

---

## Phase 2: Foundational (blocks all stories)

- [x] T003 Domain records in `domain/comparison.py` per data-model.md (ComparisonRequest,
  Difference, SourceRelation, ProcessingDifference, SnapshotDiff, ComparisonEvidence,
  ComparisonResult) with invariants: difference type/evidence/coverage rules, per-side snapshot
  IDs of envelopes and citations, difference IDs resolving on their side; tests in
  `tests/unit/test_comparison_domain.py`
- [x] T004 Two-snapshot fixture builder `tests/helpers/comparison_fixtures.py` on top of the F004
  helpers: left/right snapshots with a changed file, an unchanged file, a source only on the right,
  a requirement record unchanged / changed / right-only, a conflicting pair and an injection
  excerpt (SYNTHETIC)
- [x] T005 Refactor `answers/service.py`: `answer_in_slot(request, request_id, emit, deadline)`
  runs the flow without taking the queue slot and returns `(envelope, evidence items)`; `answer`
  keeps its behaviour. The full F005 suite must stay green; add a unit test that `answer_in_slot`
  does not touch the queue
- [x] T006 [P] `answers/citations.py` `SourceLinks.from_locks(paths)` (current lock + archived
  `data/source-locks/*.json`), still requiring an exact (source, revision) match on pinned git
  sources; the sync writes an archive copy of each written lock (research R7); tests in
  `tests/unit/test_source_links_archive.py` and the existing sync tests

**Checkpoint**: full gate green; commit.

---

## Phase 3: User Story 3 — Snapshot metadata (P2, but foundational for US1/US2)

- [x] T007 [P] [US3] Tests in `tests/unit/test_comparison_metadata.py`: relations same /
  different / left_only / right_only, revision statuses, processing differences (chunker, embedding
  digest, corpus schema), warnings `identical_revisions`, `source_only_on_one_side`,
  `unverified_revision`, `source_not_ok`, `release_label` always null
- [x] T008 [US3] Implement `comparison/metadata.py` `snapshot_diff(left, right)` from manifests
- [x] T009 [P] [US3] `comparison/coverage.py`: coverage reason for a source/record missing on a
  side (`source_absent`, `source_failed`, `source_partial`, `record_not_found`,
  `record_without_excerpt`, `not_retrieved`, `no_evidence`), with unit tests
- [x] T010 [US3] `GET /api/v1/snapshots/diff` in `api/compare_routes.py` and
  `snapshots diff LEFT RIGHT [--json]` in `cli/snapshots.py` (help line per contracts/cli.md);
  contract tests `tests/contract/test_snapshot_diff_api.py` (200, 422 identical/malformed, 404,
  cross-site 403, no runtime call) and CLI tests

---

## Phase 4: User Story 1 — Compare answers (P1) 🎯 MVP

- [x] T011 [P] [US1] `comparison/policy.py` (versioned comparison policy, output schema per
  contracts/comparison-schema.md) and `comparison/prompt.py` (side-namespaced, escaped blocks
  with snapshot attributes, cited-first ordering, split budget with a reduction warning); tests in
  `tests/unit/test_comparison_prompt.py`
- [x] T012 [P] [US1] Tests for every validation code in `tests/unit/test_comparison_validate.py`
  (JSON_INVALID … EMPTY_STATEMENT, including `CHANGED_WITHOUT_DIFFERENCE` and `DELETION_CLAIM`
  wording variants), then implement `comparison/validate.py`
- [x] T013 [P] [US1] Exact-record comparison `comparison/records.py` (fingerprint = type, title,
  status, options, first-chunk text; location-only changes noted, not counted); tests in
  `tests/unit/test_comparison_records.py` (unchanged, changed with named fields, one-sided,
  without excerpt)
- [x] T014 [US1] `comparison/service.py` `ComparisonService.compare(request, request_id,
  progress)`: identity check → validate request → pin both snapshots for the whole request → one
  slot → per-side `answer_in_slot` → comparison evidence (L/R citations from provenance) →
  deterministic differences → comparison step, repair ×1, deterministic-only fallback → server
  coverage reasons → result; `comparison.deadline_seconds`; progress with side
- [x] T015 [US1] Integration tests `tests/integration/test_comparison_service.py`: changed topic,
  unchanged topic, conflicting pair, repair success, repair failure → deterministic only with a
  warning, a side with extractive fallback, a side without evidence (no comparison call), exact-ID
  question, one side degraded to keyword search with a per-side warning
- [x] T016 [US1] Isolation tests `tests/integration/test_comparison_isolation.py`: zero cross-side
  citations across all fixture cases; activation/retirement mid-comparison via the `after_retrieval`
  seam keeps both snapshots; pins are held until the result is built
- [x] T017 [US1] `POST /api/v1/compare` JSON + SSE in `api/compare_routes.py`, registered in
  `api/app.py` and `cli/serve.py`; contract tests `tests/contract/test_compare_api.py` (validation
  422 incl. same snapshot and a `history` field, 404/409, 503, 504, cross-site 403, no bodies in
  logs) and `tests/contract/test_compare_stream.py` (event order and sides, no text before
  `comparison`, error after headers, disconnect releases the slot within 2 s, 429 while chat holds
  the slot)
- [x] T018 [US1] `compare` CLI in `cli/compare.py` registered in `cli/main.py`: text output per
  contracts/cli.md, `--json`, `--show-evidence`, exit codes; tests in
  `tests/contract/test_cli_compare.py`
- [x] T019 [US1] Readiness: `compare` available when chat is available and ≥ 2 snapshots are
  queryable, otherwise the chat reasons or `snapshots_insufficient`; `limits` adds
  `comparison_deadline_seconds`; tests in the readiness/capabilities contract tests

**Checkpoint**: full gate green; commit and push.

---

## Phase 5: User Story 2 — Missing coverage (P1)

- [x] T020 [US2] Integration tests in `tests/integration/test_comparison_service.py`: content from
  a right-only source → `not_established` / `source_absent` / missing_side left; a record only on
  the right while both have the source → `record_not_found`; a model draft saying "was removed" →
  repair, then `not_established` or deterministic only, and zero deletion wording in the result;
  one side without evidence → `insufficient_evidence` side and only `not_established`
  differences
- [x] T021 [US2] Make any failing US2 test pass in `comparison/service.py`/`validate.py`/
  `coverage.py`

---

## Phase 6: User Story 4 — Compare tab and export (P2)

- [x] T022 [P] [US4] Extract the SSE reader into `frontend/src/api/sse.ts` (chat keeps working, its
  tests unchanged); add `frontend/src/api/compare.ts` (JSON, stream, snapshot diff) with tests in
  `frontend/test/api/compare.test.ts`
- [x] T023 [P] [US4] `frontend/src/comparison/model.ts` (view models) and `export.ts` (Markdown/
  JSON with question, both snapshot IDs, per-source revisions, both answers, differences with side
  evidence, model identity, no absolute paths)
- [x] T024 [US4] Components `ComparePanel.tsx`, `DifferenceList.tsx`, `SnapshotDiffTable.tsx`, and
  a "Compare" tab in `App.tsx`: pickers with defaults, same-snapshot block, fewer-than-two message,
  progress with side, Stop (abort), side-labelled answers (reusing `AnswerView`), difference type
  labels, evidence buttons opening `EvidencePanel` with the side's citation, the metadata table
  with "No release label" note, comparison export
- [x] T025 [US4] Tests `frontend/test/components/compare.test.tsx` (flow, same-snapshot block,
  per-side citation dialog, stop aborts, export content), axe + keyboard cases in
  `frontend/test/a11y/accessibility.test.tsx`, and the Compare flow in
  `frontend/test/privacy/no-storage-writes.test.tsx`

**Checkpoint**: backend + frontend gates green; commit and push.

---

## Phase 7: User Story 5 — Benchmark (P3)

- [x] T026 [US5] `comparison/evaluation.py` (case file model, metrics: type agreement, isolation
  violations, citation integrity, deletion claims, timings; labels) and `eval comparison` in
  `cli/evaluate.py`; tests `tests/unit/test_comparison_evaluation.py` and
  `tests/contract/test_cli_eval_comparison.py`
- [x] T027 [US5] Build the real baseline: choose older commits, write
  `config/sources-baseline.yaml`, run quickstart §0 (sync with the lock backup/restore, build
  without activation) and record commands and results in `verification.md`
- [x] T028 [US5] Author `eval/comparison-dev.yaml` (≥ 10 cases from the two real snapshots: ≥ 2
  missing coverage, ≥ 2 unchanged, ≥ 1 exact ID) with a test enforcing the minimums; run
  `eval comparison` for real and record the metrics (development measurement)
- [x] T029 [US5] `real_runtime` comparison test in `tests/integration/test_real_runtime.py`
  (baseline vs active when present, else skipped) and the SC-006 timing (warm single answer vs
  warm comparison)

---

## Phase 8: Polish

- [ ] T030 [P] Docs: README, CLAUDE.md commands, `docs/user/local-ui.md` (Compare tab),
  `docs/user/comparison.md` (baseline procedure, reading differences, the no-deletion rule)
- [ ] T031 [P] `docs/BACKLOG.md`, `docs/TRACEABILITY.md` (RET-006, ANS-005, ANS-007, SRC-003,
  AT-03, AT-10, AT-17), `docs/ASSUMPTIONS.md` (A-041 onward)
- [ ] T032 Full local gate and HTTP smoke test on the real server (compare JSON + SSE, diff
  endpoint, no question text in the log); record in `verification.md`
- [ ] T033 Walk quickstart §A–§E and record the results; the browser part of §D is recorded as "not
  run — no browser on this machine, deferred to the owner"

---

## Dependencies & Execution Order

Setup → Foundational → US3 metadata/coverage (used by US1/US2) → US1 → US2 → US4 → US5 → Polish.
US4 needs the US1 HTTP contract. US5's real run needs the baseline (T027), which can run any time
after T006 (the lock archive).

## Parallel Opportunities

T001/T002; T006 with T003–T005; T007/T009; T011/T012/T013; T022/T023; T030/T031.

## Implementation Strategy

MVP = Phases 1–4 (the CLI/HTTP comparison with metadata). Then add the missing-coverage hardening,
the UI, and the benchmark. Commit at each checkpoint after the gate passes.
