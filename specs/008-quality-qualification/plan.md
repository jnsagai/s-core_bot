# Implementation Plan: F008 Quality Qualification and Release Evidence

**Branch**: `008-quality-qualification` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-quality-qualification/spec.md`

## Summary

Add a `qualification/` package and commands that produce release evidence without ever
overstating it:
- a 100-case suite (60 development / 40 held-out, frozen by hash) with the full master §13.2
  schema;
- a suite harness with repeated runs and review sheets;
- a human-review import that alone can unblock the human-judged metrics;
- an extended synthetic adversarial suite run with the real models on a throwaway snapshot;
- a no-root blocked-egress check in a loopback-only network namespace;
- a performance harness for the master §13.4 budgets;
- a model qualification record;
- a traceability checker in CI;
- a declarative release-gate file with a `release report` command that marks every gate `pass`,
  `fail`, `blocked` or `not run` from recorded evidence, with sections per evidence kind.

## Technical Context

**Language/Version**: Python 3.12; Bash for the namespace wrapper

**Primary Dependencies**: no new packages (Pydantic, PyYAML, httpx, Typer, stdlib
`xml.etree` for JUnit, `resource`, `subprocess` for `nvidia-smi`/`unshare`)

**Storage**: committed case and gate files under `eval/`; generated reports under `data/reports/`;
the F008 evidence copy of the release report under `docs/quality/`

**Testing**: pytest with the socket guard, fake providers and fixture snapshots for every harness;
the `real_runtime` marker for real runs; the traceability checker as a test

**Target Platform**: the reference Linux GPU workstation (Ollama 0.34.0 snap)

**Project Type**: single Python project (CLI + library + local service)

**Performance Goals**: harness overhead negligible; the full suite runs ≈ 100 × 4 s per split pass

**Constraints**: no downloads; loopback only; no question/answer logging; no synthetic "pass"
results; never mark a human review

**Scale/Scope**: 100 suite cases, ≥ 10 hostile cases, ≥ 50 performance queries

## Constitution Check

| Principle | Status | How this plan complies |
| --- | --- | --- |
| I. Local operation | PASS | Evaluation uses only the loopback runtime; the offline check proves it with egress blocked; `models qualify` reads local metadata only. |
| II. Evidence precedes assertions | PASS | Every gate cites an evidence file; missing evidence is `not run`. |
| III. Snapshots explicit | PASS | Reports record snapshot and model identities; the adversarial suite uses a throwaway snapshot and never touches the real catalog. |
| IV. Documentation untrusted | PASS | Hostile documents are synthetic and marked; they are never added to the real corpus. |
| V. Read-only assistance | PASS | No tools; judges only read outputs. |
| VI. Modular monolith | PASS | New `qualification/` package reusing retrieval/answers services via DI. |
| VII. Honest verification | PASS | Core of the feature: evidence kinds separated, human gates blocked without a human review, development measurements labelled, held-out freeze before use. |
| VIII. Privacy | PASS | Log scans for question text during runs; no persistence of conversations. |
| IX. Spec-first | PASS | Traceability checker enforces complete mapping. |
| X. Public profile separate | PASS | PUB requirements reported as deferred to F010. |
| XI. Licenses follow artifacts | PASS | Model licenses read from the local artifacts and recorded; the license gate stays in CI. |
| XII. No implied authority | PASS | The report never says "approved"; the agent review is labelled; the verdict is `ready` only with all required evidence. |

Post-design re-check: **PASS**.

## Project Structure

```text
specs/008-quality-qualification/ spec, plan, research, data-model, quickstart, contracts/, checklists/, tasks, verification
eval/suite/dev.yaml, heldout.yaml, heldout.freeze.json
eval/hostile/*.rst, eval/hostile/cases.yaml
eval/release-gates.yaml
docs/quality/review-rubric.md, docs/quality/release-report-<date>.md
scripts/offline_check.sh, scripts/check_traceability.py
src/score_docs_assistant/qualification/
├── __init__.py
├── suite.py          # SuiteCase/SuiteFile, loading, composition checks, freeze manifest
├── harness.py        # run_suite(): retrieval + answers + metrics + privacy scan; combine runs
├── review.py         # review sheet generation, import → HumanReview
├── adversarial.py    # throwaway hostile snapshot, real-model run, judges
├── offline.py        # in-namespace HTTP probe (python -m ...)
├── performance.py    # timings, cold unload, cancellation, memory sampling, budgets
├── models.py         # model qualification from lock + /api/show
├── junit.py          # JUnit XML parsing
├── gates.py          # gate file model + evaluation against evidence
└── report.py         # release report Markdown/JSON
src/score_docs_assistant/cli/qualify.py   # eval suite|freeze|review|adversarial|performance, models qualify, release report
tests/unit/test_suite_files.py, test_freeze.py, test_harness.py, test_review.py, test_gates.py,
      test_release_report.py, test_junit.py, test_traceability.py, test_model_qualification.py,
      test_performance.py, test_adversarial_judges.py
tests/integration/test_adversarial_snapshot.py, tests/contract/test_cli_qualify.py,
tests/integration/test_real_runtime.py (+ adversarial smoke)
```

## Key Design Decisions

1. Evidence is read from files, never typed; gates are declarative (R8).
2. Human-judged gates can only be unblocked by an imported sheet that has a reviewer and a date
   (R4).
3. Held-out freeze committed before the first held-out run (R2).
4. Blocked egress without root through a user network namespace and a private runtime reading the
   installed models (R6).
5. The adversarial suite runs on a throwaway snapshot built by the production pipeline (R5).
6. Critical failures (isolation, injection) force the verdict to `blocked` (FR-015).

## Verification Strategy

| Requirement | Verification |
| --- | --- |
| FR-001–FR-003, SC-003 | unit: suite files validate, counts, stratification, freeze mismatch fails, held-out run refused |
| FR-004–FR-006, SC-002 | unit: sheet generation, import validation (mismatch, missing reviewer, partial), metrics with denominators |
| FR-007–FR-009, SC-008 | unit/integration with fake providers: metrics, runs/spread, labels, privacy scan; real: dev run, held-out × 3 |
| FR-010, SC-005 | unit: judges; integration: throwaway hostile snapshot with fakes; real: adversarial run |
| FR-011, SC-004 | real: `scripts/offline_check.sh` result; unit: probe logic with a fake server |
| FR-012 | privacy scan in suite runs; frontend checks collected |
| FR-013, FR-014, SC-006 | unit: percentile/budget logic, insufficient sample; real performance run |
| FR-015, SC-001 | unit: gate evaluation for every status path, verdict; real report generated and committed |
| FR-016, SC-007 | the checker as a test and in CI |
| FR-017 | unit with a fake runtime; real `models qualify` |
| FR-018 | socket guard in all tests; no pull code path |

## Complexity Tracking

No constitution violations; section intentionally empty.
