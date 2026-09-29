# Implementation Plan: F007 Explicit Snapshot Comparison

**Branch**: `007-version-comparison` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-version-comparison/spec.md`

## Summary

Add a `comparison/` package that compares how two explicitly chosen snapshots answer one question.
`ComparisonService` checks the model identity, pins both snapshots for the whole request, holds
the single generation slot, and runs the F005 pipeline once per side (refactored into
`AnswerService.answer_in_slot`). It then runs one validated comparison step over side-namespaced
evidence (`L…`/`R…`), with at most one repair and otherwise deterministic differences only. It also
adds two deterministic comparisons: per-source snapshot metadata (`SnapshotDiff`) and exact
requirement records. Coverage reasons are derived by the server, and removal or addition wording is
rejected. The feature is exposed as `POST /api/v1/compare` (JSON/SSE),
`GET /api/v1/snapshots/diff`, the `compare` and `snapshots diff` CLI commands, a Compare tab with
export in the web UI, and `eval comparison` over a ≥ 10-case suite run on a real baseline snapshot
built from older upstream commits.

## Technical Context

**Language/Version**: Python 3.12; TypeScript (frontend, unchanged toolchain)

**Primary Dependencies**: no new packages. FastAPI, Pydantic, httpx, PyYAML; React/Vite/Vitest.

**Storage**: none new server-side. `data/source-locks/<sha>.json` archives (R7); reports under
`data/reports/`; `eval/comparison-dev.yaml` and `config/sources-baseline.yaml` are committed.

**Testing**: pytest with the socket guard; F004 fixture snapshot builders extended to two
snapshots with controlled differences (changed file, unchanged file, source present on one side
only, a requirement record changed / unchanged / one-sided); the scripted
`FakeGenerationProvider` for answers and the comparison step; TestClient and httpx ASGI transport
for SSE, disconnect and queue tests; Vitest + jsdom for the Compare tab. The `real_runtime` marker
covers the real comparison run.

**Target Platform**: Linux x86-64 reference workstation.

**Project Type**: single Python project (CLI + library + local HTTP service) with the F006 static
frontend.

**Performance Goals**: warm comparison ≤ 3 × a single warm answer (SC-006); deadline 240 s.

**Constraints**: loopback only; one active generation; the comparison holds its slot for the whole
request; no unvalidated difference or claim leaves the server; no bodies in logs; no release label
inference.

**Scale/Scope**: two snapshots per request; ≥ 10 benchmark cases.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Status | How this plan complies |
| --- | --- | --- |
| I. Local operation | PASS | Only the loopback runtime with the locked digest. The baseline `sources sync` is an explicit networked ingestion command, never part of the serve path. |
| II. Evidence precedes assertions | PASS | Every difference cites side evidence built from stored provenance; absence is `not_established` with a server-derived reason; deletion wording is rejected. |
| III. Snapshots explicit | PASS | Both snapshot IDs are required and pinned for the whole request; envelopes stay single-snapshot; the side of every citation is checked by invariants. |
| IV. Documentation untrusted | PASS | Both evidence blocks are escaped and delimited data; the F005 injection heuristics apply per side and in the comparison step. |
| V. Read-only assistance | PASS | No tools; commands remain text. |
| VI. Modular monolith | PASS | New `comparison/` package, domain records free of FastAPI/Ollama types, reuse of `SearchService`/`AnswerService` through dependency injection. |
| VII. Honest verification | PASS | Fake-provider tests labelled as such; the real benchmark is recorded as a development measurement; browser checks are deferred to the owner. |
| VIII. Privacy | PASS | Stateless; no question/answer logging; the UI keeps results in memory only. |
| IX. Spec-first | PASS | RET-006, ANS-005, ANS-007, SRC-003 are mapped in TRACEABILITY. |
| X. Public profile separate | PASS | Guard and bind unchanged; bounded queue shared with chat. |
| XI. Licenses follow artifacts | PASS | Citations keep source attribution; no new dependencies. |
| XII. No implied authority | PASS | No release label is inferred; unverified revisions are flagged; no approval wording. |

Post-design re-check: **PASS**. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/007-version-comparison/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/ http-api.md, cli.md, comparison-schema.md
├── checklists/ requirements.md, comparison.md
├── tasks.md
└── verification.md
```

### Source Code (repository root)

```text
src/score_docs_assistant/
├── domain/comparison.py          # ComparisonRequest, Difference, SourceRelation, SnapshotDiff,
│                                 # ComparisonEvidence, ComparisonResult, evaluation records
├── config/schema.py              # + ComparisonConfig (`comparison` section)
├── answers/service.py            # refactor: answer_in_slot() returns (envelope, evidence items)
├── answers/citations.py          # SourceLinks.from_locks (current + archived locks, R7)
├── comparison/
│   ├── __init__.py
│   ├── metadata.py               # snapshot_diff(left_manifest, right_manifest) → SnapshotDiff
│   ├── records.py                # exact-record comparison across two EntityIndexes
│   ├── coverage.py               # coverage reasons from manifests
│   ├── policy.py                 # comparison policy + output schema
│   ├── prompt.py                 # side-namespaced evidence blocks
│   ├── validate.py               # difference validation (R3)
│   ├── service.py                # ComparisonService (pins, slot, deadline, progress)
│   └── evaluation.py             # case file, metrics, report
├── ingestion/ (sync)             # archive written locks to data/source-locks/ (R7)
├── readiness.py                  # compare capability for real
├── api/compare_routes.py         # POST /api/v1/compare (JSON + SSE), GET /api/v1/snapshots/diff
├── api/app.py, api/schemas.py    # register routes; limits.comparison_deadline_seconds
├── cli/compare.py                # `compare`
├── cli/snapshots.py              # + `snapshots diff`
├── cli/evaluate.py               # + `eval comparison`
└── cli/serve.py                  # build ComparisonService
config/sources-baseline.yaml      # older pinned commits, no needs exports (R9)
eval/comparison-dev.yaml          # ≥ 10 cases (reviewed: false)
frontend/src/
├── api/sse.ts                    # shared SSE-over-fetch reader (extracted from chat.ts)
├── api/compare.ts                # compare JSON/stream, snapshot diff
├── comparison/model.ts, export.ts
└── components/ComparePanel.tsx, DifferenceList.tsx, SnapshotDiffTable.tsx
tests/
├── helpers/comparison_fixtures.py
├── unit/ test_comparison_metadata.py, test_comparison_records.py, test_comparison_validate.py,
│         test_comparison_prompt.py, test_comparison_domain.py, test_comparison_evaluation.py,
│         test_source_links_archive.py
├── contract/ test_compare_api.py, test_compare_stream.py, test_snapshot_diff_api.py,
│             test_cli_compare.py, test_cli_eval_comparison.py
└── integration/ test_comparison_service.py, test_comparison_isolation.py,
                 test_real_runtime.py (+ comparison)
frontend/test/ components/compare.test.tsx, a11y (Compare cases), privacy (Compare flow)
```

**Structure Decision**: comparison is a separate package, like `answers/`, because it has its own
policy, validator and evaluation. It depends on `answers/` and `retrieval/`; nothing depends on it
except the API, CLI and readiness layers.

## Key Design Decisions

1. **Per-side F005 answers + one comparison step** (R1): no envelope mixes versions.
2. **Side-namespaced evidence with invariants** (R2): isolation is checked by construction.
3. **Unconditional no-deletion rule** (R3, R4): absence is `not_established` with a
   server-derived reason.
4. **Deterministic metadata and record comparisons** (R5): useful without the model and a
   fallback when the comparison step fails.
5. **No release labels** (R6).
6. **Archived locks for immutable links to older revisions** (R7).
7. **One slot, one deadline, shared queue** (R8).
   Differences are ordered deterministic first (coverage, exact records), then model differences.
8. **Real baseline snapshot from pinned older commits** (R9), never activated.

## Verification Strategy

| Requirement | Verification (layer) |
| --- | --- |
| FR-001, FR-015 | contract: request validation (same ID, missing ID, history field → 422) |
| FR-002 | integration: activation/retirement mid-comparison via test seam; both sides keep their snapshots; pins held |
| FR-003, SC-001 | integration + domain: invariants reject cross-side citations; fixture comparison has 0 isolation violations |
| FR-004–FR-008 | unit: every validation code; integration: repair then deterministic fallback; conflicting fixture |
| FR-009, FR-010, FR-012, SC-004 | unit: `snapshot_diff` relations/warnings; contract: diff endpoint and CLI |
| FR-011 | unit: record comparison unchanged/changed/one-sided/no-excerpt |
| FR-013, FR-014 | contract/integration: SSE order and sides, 429 with chat running, disconnect releases slot, deadline 504 |
| FR-016 | contract: no bodies in logs; cross-site 403 |
| FR-017 | contract: CLI help lines, text/JSON output, exit codes |
| FR-018, FR-019, SC-003 | Vitest: Compare tab, same-snapshot block, per-side citation dialog, export content, axe + keyboard; browser walkthrough deferred to the owner |
| FR-020, SC-005 | unit: metrics; real: benchmark over baseline vs active recorded |
| SC-002 | validator unit tests + missing-coverage fixtures + benchmark deletion count |
| SC-006 | real: timing of a warm comparison vs a warm single answer |

## Complexity Tracking

No constitution violations; section intentionally empty.
