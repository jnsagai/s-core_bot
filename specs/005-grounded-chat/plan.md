# Implementation Plan: F005 Grounded Local Answers

**Branch**: `005-grounded-chat` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-grounded-chat/spec.md`

## Summary

Add an `answers/` package that turns a question into a validated, cited answer from one pinned
snapshot. It reuses F004 retrieval, packs whole excerpts into a conservative token budget with
request-local evidence IDs, and calls the locked local model through a new
`OllamaGenerationProvider` (JSON-schema structured output, low temperature, thinking off when
advertised, streamed internally for cancellation, no tools). It validates the draft (schema,
evidence membership, status/claim consistency, quotes, URLs), allows at most one repair, and
otherwise returns a labelled extractive fallback. Citations are built only from stored provenance,
with immutable GitHub links when the revision is provably pinned. A single-slot generation queue
with bounded waiters, one deadline and disconnect-driven cancellation backs `POST /api/v1/chat`
(JSON or SSE progress stream) and the `ask` CLI. Readiness reports chat for real. `eval answers`
measures status agreement, citation integrity and evidence overlap, and emits a human review sheet.

## Technical Context

**Language/Version**: Python 3.12 (unchanged)

**Primary Dependencies**: no new packages. FastAPI/Starlette (`StreamingResponse`,
`run_in_threadpool`), httpx (async streaming to Ollama), Pydantic, PyYAML; F004 `SearchService`;
F001 model lock; F003 token estimate.

**Storage**: none server-side (stateless chat). Evaluation reports and review sheets go to
`data/reports/`; the case file `eval/answers-dev.yaml` is committed.

**Testing**: pytest with the socket guard. A `FakeGenerationProvider` (scripted outputs per call,
delays, failures, cancellation observation) is used via dependency injection. Fixture snapshots
come from F004 helpers plus a SYNTHETIC hostile/conflict/injection fixture source. HTTP uses
TestClient (JSON and SSE) and httpx `AsyncClient` with ASGI transport for disconnect and
concurrency tests. The `real_runtime` marker covers real generation, real injection cases and real
evaluation.

**Target Platform**: Linux x86-64; reference GPU workstation for real measurements.

**Project Type**: single Python project, CLI + library + local HTTP service.

**Performance Goals**: warm answer ≈ 3 s measured (R1); master target p95 ≤ 30 s warm for ≤ 500
output tokens is well above that. Deadline 120 s.

**Constraints**: loopback only; one active generation; ≤ 4 queued; deadline covers everything; ≤ 1
repair; never stream unchecked text; never log question/history/answer text; no tools; no
fallback provider.

**Scale/Scope**: one user machine; ≥ 20 answer cases (≥ 5 unanswerable, ≥ 3 injection).

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Status | How this plan complies |
| --- | --- | --- |
| I. Local operation | PASS | Only the loopback Ollama runtime; the model digest must match the lock; no cloud or paid fallback exists in the code path (FR-014, FR-015). |
| II. Evidence precedes assertions | PASS | Documented claims must cite supplied evidence IDs; citations and URLs come from stored provenance only; `insufficient_evidence` without a model call when there is no evidence; extractive fallback is verbatim stored text. |
| III. Snapshots explicit | PASS | One pinned snapshot per request (F004), its ID and model identity in every envelope; follow-ups with another snapshot start a new evidence context. |
| IV. Documentation untrusted | PASS | Evidence and history are delimited data with escaped delimiters; the policy states they are not instructions; injection fixtures verify it; no rendering of HTML. |
| V. Read-only assistance | PASS | No tools or function calls are passed to the model; nothing in answers is executed; commands stay inert text. |
| VI. Modular monolith | PASS | `GenerationProvider` protocol (master spec §5.1) with an Ollama implementation; `answers/` package; domain records free of FastAPI/Ollama types; no new services. |
| VII. Honest verification | PASS | Fake-provider tests labelled mocked; real-model runs recorded separately; human-judged metrics "not run" until reviewed; blocked-egress constraint recorded honestly. |
| VIII. Privacy | PASS | Question/history/answer never logged; stateless server; no telemetry. |
| IX. Spec-first | PASS | ANS-001–012, RET-005, LOC-002, SEC-001, OPS-006 mapped; TRACEABILITY updated. |
| X. Public profile separate | PASS | Loopback bind and guard unchanged; bounded queue and deadlines apply in the local profile. |
| XI. Licenses follow artifacts | PASS | Citations keep source attribution; license-review flags remain visible via F004 sources. |
| XII. No implied authority | PASS | Policy forbids certification/approval/exhaustiveness claims without support; statuses never imply approval. |

Post-design re-check: **PASS**. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/005-grounded-chat/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/ http-api.md, cli.md, answer-schema.md
├── checklists/ requirements.md (+ checklist phase)
├── tasks.md
└── verification.md
```

### Source Code (repository root)

```text
src/score_docs_assistant/
├── domain/answers.py            # ChatRequest, Turn, Claim, Citation, AnswerEnvelope,
│                                # GenerationIdentity, evaluation records
├── domain/errors.py             # + GenerationError (code, http_status, retryable)
├── config/schema.py             # + GenerationConfig
├── models/runtime.py            # GenerationProvider protocol (identity, capabilities, chat stream)
├── models/ollama_chat.py        # OllamaGenerationProvider (async httpx, format schema, think flag)
├── answers/
│   ├── __init__.py
│   ├── policy.py                # versioned system policy + output JSON schema
│   ├── prompt.py                # evidence packing, delimiters/escaping, history selection, budget
│   ├── validate.py              # draft parsing + validation rules → errors
│   ├── citations.py             # citations from stored provenance, immutable URLs from the lock
│   ├── fallback.py              # extractive fallback
│   ├── queue.py                 # GenerationQueue (1 active, bounded waiters, positions)
│   ├── service.py               # AnswerService: request → envelope (deadline, repair, progress)
│   └── evaluation.py            # answer cases, report, review sheet
├── api/chat_routes.py           # POST /api/v1/chat (JSON + SSE, disconnect handling)
├── api/app.py                   # register chat routes with an AnswerService
├── readiness.py                 # chat availability without not_implemented
├── cli/ask.py                   # `ask`
├── cli/evaluate.py              # + `eval answers`
└── cli/serve.py                 # build AnswerService
eval/answers-dev.yaml            # ≥ 20 cases (real snapshot) + injection cases (synthetic snapshot)
tests/
├── helpers/fake_generation.py   # scripted provider
├── helpers/hostile_sources.py   # SYNTHETIC conflict/injection/no-answer fixture source
├── unit/ test_generation_config.py, test_policy_prompt.py, test_validate.py, test_citations.py,
│         test_fallback.py, test_queue.py, test_ollama_chat.py, test_answer_evaluation.py
├── contract/ test_chat_api.py, test_chat_stream.py, test_cli_ask.py, test_cli_eval_answers.py
└── integration/ test_answer_service.py, test_injection.py, test_chat_admission.py,
                 test_real_runtime.py (+ generation, injection, eval)
```

**Structure Decision**: master spec §14 names `answers/` for "context assembly, prompts,
validation" and `models/` for providers. The API routes live in their own module like F004's.

## Key Design Decisions

1. **Validate, repair once, then fall back** (R4, R5): the unchecked draft never leaves the server.
2. **Status/claim consistency enforced** (R4): the model's status field is not trusted alone
   (real observed failure).
3. **Delimited, escaped data blocks** (R3): evidence/history cannot close their block or pose as
   policy.
4. **Citations from provenance only** (R6): immutable URLs only on an exact revision match; model
   URLs rejected.
5. **One deadline, one slot, bounded waiters** (R7): cancellation closes the provider stream.
6. **Conservative budget** (R2): no silent prompt truncation; reductions reported.
7. **Measured quality** (R9): automated integrity and status metrics now; human support review via
   the sheet; "not run" until then.

## Verification Strategy

| Requirement | Verification (layer) |
| --- | --- |
| FR-001, FR-002, FR-003 | integration: answer flow with fake provider → envelope fields, status/claim rules; snapshot pinning with an activation mid-generation |
| FR-004, FR-005, FR-006 | unit: citations from provenance, GitHub URL only on exact revision match, none for exports; model URLs rejected; commands stay text |
| FR-007, FR-008, FR-009, SC-002 | unit: every validation code; integration: repair success, repair failure → fallback, no evidence → `insufficient_evidence` without a model call, `ANSWER_INVALID` only without evidence |
| FR-010, FR-011, SC-004 | unit: policy text/version, delimiters and escaping; integration + real_runtime: injection fixtures (policy override, prompt disclosure, command execution requests) |
| FR-012, FR-013 | unit: budget packing (evidence then history reduction, warnings, never over budget); provider request body (schema, temperature, `think` only when advertised, no tools) |
| FR-014, FR-015, SC-003 | unit/integration: identity mismatch, missing model, unreachable → `GENERATION_UNAVAILABLE`; search unaffected; socket guard proves loopback only |
| FR-016, FR-017 | unit: history limits/roles, retrieval query composition, snapshot-bound turns excluded with warning |
| FR-018–FR-020, SC-005 | integration: slot + queue limits (429), queue positions, deadline 504, disconnect releases within 2 s and closes the provider stream |
| FR-021, FR-022 | contract: SSE framing and order, no claim text before `answer`, error-after-headers; unknown fields 422; cross-origin 403; no bodies in logs |
| FR-023 | contract: readiness chat available / unavailable reasons; search independent |
| FR-024 | contract: `ask` help, text/JSON/`--show-evidence`, exit codes |
| FR-025, FR-026, SC-006 | unit: evaluation metrics and review sheet; real: `eval answers` run recorded |
| SC-001 | every test asserting envelopes checks citation integrity; evaluation reports it on real runs |
| SC-007 | real: blocked-egress run or recorded deviation plus socket-guard evidence |

## Complexity Tracking

No constitution violations; section intentionally empty.
