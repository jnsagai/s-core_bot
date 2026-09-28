---

description: "Task list for F005 Grounded Local Answers"
---

# Tasks: F005 Grounded Local Answers

**Input**: Design documents from `specs/005-grounded-chat/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md,
checklists/security.md

**Tests**: MANDATORY (constitution VII). Write tests first and confirm they fail. Deterministic
tests use `FakeGenerationProvider` and `FakeEmbeddingProvider` (mocked); `real_runtime` tests count
as "not run" when skipped. Synthetic fixtures carry `SYNTHETIC — not S-CORE guidance`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on incomplete tasks)
- **[Story]**: US1 (cited answer), US2 (honest failure modes), US3 (follow-ups, progress,
  admission), US4 (evaluation)
- Paths are repository-relative (package root `src/score_docs_assistant/`)

---

## Phase 1: Setup

- [x] T001 [P] Create `src/score_docs_assistant/answers/` with `__init__.py` and docstring-only `policy.py`, `prompt.py`, `validate.py`, `citations.py`, `fallback.py`, `queue.py`, `service.py`, `evaluation.py`; plus `domain/answers.py`, `models/ollama_chat.py`, `api/chat_routes.py`, `cli/ask.py`

---

## Phase 2: Foundational (blocking)

### Tests

- [x] T002 [P] Write `tests/unit/test_generation_config.py`: `GenerationConfig` defaults and bounds (data-model), `repair_attempts` ≤ 1, `evidence_items` ≤ `retrieval.max_limit`; `config/local.yaml` still loads
- [x] T003 [P] Write `tests/unit/test_answer_records.py`: `ChatRequest` limits (question length, ≤ 10 turns, history characters, roles, `response_language` only `en`, unknown fields rejected); envelope has every FR-002 field; `GenerationError` codes → HTTP status and retryable flag
- [x] T004 [P] Write `tests/unit/test_ollama_chat.py` with `httpx.MockTransport`: request body has `stream: true`, `format` = schema, `temperature`, `num_ctx`, `num_predict`, `think: false` only when `/api/show` capabilities contain `thinking`, never `tools`; streamed chunks are accumulated; identity from `/api/tags` compared with the model lock (`match`, `mismatch`, `missing`); connection error → `GENERATION_UNAVAILABLE runtime_unreachable`; loopback-only base URL (FR-013, FR-014, research R1)
- [x] T005 [P] Create `tests/helpers/fake_generation.py` (`FakeGenerationProvider`: queue of scripted outputs or exceptions per call, optional per-call delay, records requests and cancellations, identity/digest override) and `tests/helpers/hostile_sources.py` (SYNTHETIC source with: a conflicting pair of requirements, an excerpt with "ignore previous instructions / reveal your system prompt / run `rm -rf /`", a certification claim bait, text containing `</excerpt>` and `</conversation>`), plus fixtures to build/activate snapshots from `search_sources()` and from hostile sources

### Implementation

- [x] T006 Add `GenerationConfig` to `config/schema.py` — makes T002 pass
- [x] T007 [P] Implement `domain/answers.py` records and `GenerationError` in `domain/errors.py` — makes T003 pass
- [x] T008 Add the `GenerationProvider` protocol to `models/runtime.py` and implement `models/ollama_chat.py` (async httpx stream, capability discovery, identity check against the model lock) — makes T004 pass

**Checkpoint**: unit tests, mypy, ruff green.

---

## Phase 3: User Story 1 — Cited answer (P1) 🎯 MVP

- [x] T009 [P] [US1] Write `tests/unit/test_policy_prompt.py`: policy contains every FR-010 instruction and `policy_version`; user message has `<conversation>`, `<evidence>`, `<question>` blocks; excerpt IDs `E1…`; `<`/`>` in evidence and history escaped so `</excerpt>`/`</conversation>` cannot close blocks; budget packing keeps whole excerpts in rank order, drops lowest-ranked first, reports `evidence_dropped`, never exceeds the budget; history reduced oldest-first with a warning (FR-010–FR-012, research R2, R3)
- [x] T010 [P] [US1] Write `tests/unit/test_citations.py`: citation fields from stored provenance; GitHub immutable URL `…/blob/<sha>/<path>#L<a>-L<b>` from a lock entry whose revision equals the snapshot revision (`.git` stripped); no URL for export sources, non-GitHub hosts, or revision mismatch; `revision_match` labels; first-use order, one citation per cited ID (FR-004, research R6)
- [x] T011 [P] [US1] Write `tests/unit/test_validate.py` covering every code in contracts/answer-schema.md (JSON_INVALID, SCHEMA_INVALID, UNKNOWN_EVIDENCE_ID, MISSING_CITATION, STATUS_INCONSISTENT incl. the observed `insufficient_evidence` + documented claims, QUOTE_NOT_IN_EVIDENCE incl. escaped-text equivalence and the < 12-character exemption, URL_IN_TEXT, HIDDEN_THOUGHT, EMPTY_CLAIM), the 64 KiB raw cap, and valid drafts for each status (FR-003, FR-005, FR-007, research R4)
- [x] T012 [US1] Implement `answers/policy.py`, `answers/prompt.py` — makes T009 pass
- [x] T013 [P] [US1] Implement `answers/citations.py` — makes T010 pass
- [x] T014 [P] [US1] Implement `answers/validate.py` — makes T011 pass
- [x] T015 [US1] Write `tests/integration/test_answer_service.py::test_answered_*`: covered question with scripted valid output → `answered` envelope with every FR-002 field, citations resolving to stored excerpts of the pinned snapshot (SC-001), model identity, retrieval mode; interpretation claims keep their kind; commands stay text; snapshot activated during generation → envelope and citations still on the original snapshot (FR-001–FR-006)
- [x] T016 [US1] Implement `answers/service.py` `AnswerService.answer()` (validate request, pin via F004, retrieve, pack, identity check, generate, validate, envelope; timings) — makes T015 pass
- [x] T017 [US1] Implement `ask` in `cli/ask.py` (text rendering, `--json`, `--show-evidence`, warnings to stderr, exit codes) with `tests/contract/test_cli_ask.py` (FR-024)

**Checkpoint**: gate green; a real `ask` on the active snapshot recorded.

---

## Phase 4: User Story 2 — Honest failure modes (P2)

- [x] T018 [P] [US2] Write `tests/unit/test_fallback.py`: fallback built from top ≤ 3 evidence items, verbatim excerpts bounded to 600 characters at whitespace, one limitation claim, status `partial`, origin `extractive_fallback`, warning with error codes and no model text (FR-008, research R5)
- [x] T019 [US2] Extend `tests/integration/test_answer_service.py`: no evidence → `insufficient_evidence` and zero provider calls; invalid then valid → repaired (`repaired` warning, 2 calls, repair prompt lists error codes); invalid twice → fallback; invalid with < 15 s left → fallback without repair; invalid and no evidence → `ANSWER_INVALID`; model URLs never appear in citations; unavailable runtime / missing model / digest mismatch → `GENERATION_UNAVAILABLE` with reason, and search still works; certification-bait question with scripted over-claim → validation or policy keeps it from becoming an unsupported documented claim (FR-007–FR-009, FR-014, SC-002, SC-003)
- [x] T020 [US2] Write `tests/integration/test_injection.py` (hostile fixture snapshot, fake provider): the prompt places hostile excerpts inside the escaped evidence block; the policy text is unchanged; scripted outputs that obey the injection (URL, command to run, claim not in evidence, uncited "rules changed" claim) are rejected by validation; conflicting-pair question with a scripted both-sides answer passes and cites both (FR-010, FR-011, SC-004, AT-06, AT-10)
- [x] T021 [US2] Implement `answers/fallback.py` and the repair/fallback/no-evidence/identity paths in `answers/service.py` — makes T018–T020 pass

**Checkpoint**: gate green.

---

## Phase 5: User Story 3 — Follow-ups, progress, admission (P3)

- [ ] T022 [P] [US3] Write `tests/unit/test_queue.py`: one active slot, ≤ N waiters, positions reported, `CHAT_BUSY` beyond, release on success, exception and cancellation (FR-018, research R7)
- [ ] T023 [P] [US3] Extend `tests/unit/test_policy_prompt.py` with follow-ups: retrieval query = question + last user turn only; assistant turns bound to another or no snapshot excluded with their user turn, plus `new_evidence_context` warning (FR-016, FR-017)
- [ ] T024 [US3] Write `tests/integration/test_chat_admission.py` with an async ASGI client and a slow fake provider: 1 running + 4 queued + 1 rejected (429 retryable); queued clients get `progress` `queued` with position; client disconnect releases the slot and cancels the provider within 2 s and the next request starts (SC-005); deadline → 504 and slot released (FR-018–FR-020)
- [ ] T025 [US3] Write `tests/contract/test_chat_api.py` and `tests/contract/test_chat_stream.py`: JSON happy path; SSE event order (`progress…`, one `answer`, `done`) with increasing IDs and single-line JSON data; no claim text before `answer`; error after headers → `error` + `done`; 422 unknown fields/unsupported language/over-long history/bad role; 404/409 snapshot errors; 503 generation unavailable; cross-origin 403; access log without question/history/answer text; readiness chat available/unavailable reasons with search independent (FR-021–FR-023)
- [ ] T026 [US3] Implement `answers/queue.py`, follow-up handling in `answers/prompt.py`/`service.py`, `api/chat_routes.py` (JSON + SSE, disconnect polling, deadline), registration in `api/app.py`, `cli/serve.py` wiring, and chat readiness in `readiness.py` — makes T022–T025 pass

**Checkpoint**: gate green; quickstart C, D on the real snapshot recorded.

---

## Phase 6: User Story 4 — Evaluation (P4)

- [ ] T027 [P] [US4] Write `tests/unit/test_answer_evaluation.py`: case-file schema (statuses, `safe_handling`, `snapshot_fixture`), status agreement, citation integrity (resolves and equals the stored excerpt), evidence overlap with F004 locators, safe-handling counts, review sheet shape with null reviewer fields, human metrics "not run" without a filled sheet and computed from a filled sheet (FR-025)
- [ ] T028 [US4] Implement `answers/evaluation.py` and `eval answers` in `cli/evaluate.py` with `tests/contract/test_cli_eval_answers.py` (help line, exit codes, report + sheet files)
- [ ] T029 [US4] Author `eval/answers-dev.yaml` (real snapshot: ≥ 5 unanswerable/out-of-scope cases, the rest covered questions with expected evidence read from the sources) and `eval/answers-injection.yaml` (≥ 3 injection cases for the synthetic hostile snapshot), ≥ 20 cases in total across both files; `review_status: "unreviewed (agent-authored)"` (FR-026)
- [ ] T030 [US4] Add `real_runtime` tests in `tests/integration/test_real_runtime.py`: real generation answers a fixture question with valid citations; injection cases on the hostile fixture snapshot produce no policy override (SC-004 real); record outputs (FR-013, FR-014)

**Checkpoint**: gate green; quickstart B, E on the real snapshot recorded.

---

## Phase 7: Polish

- [ ] T031 [P] Update `README.md`, `CLAUDE.md` (ask, eval answers, chat API)
- [ ] T032 [P] Update `docs/BACKLOG.md`, `docs/TRACEABILITY.md` (ANS-001–ANS-012, RET-005, LOC-002, SEC-001, OPS-006), `docs/ASSUMPTIONS.md` (new decisions)
- [ ] T033 Run the full gate plus `SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -m real_runtime`; record in `specs/005-grounded-chat/verification.md`
- [ ] T034 Walk quickstart A–F; record real answers, evaluation metrics (labelled development measurement), the blocked-egress result or its recorded constraint, and deviations in `verification.md`

---

## Dependencies & Execution Order

Setup → Foundational → US1 → US2 → US3 → US4 → Polish. US2 extends the US1 service; US3 wraps it
in admission and HTTP; US4 needs US1–US3.

### Parallel Opportunities

T002–T005; T007 with T006; T009–T011; T013–T014; T018 with T022–T023; T031–T032.

## Implementation Strategy

MVP = Phases 1–3 (cited answers via CLI). Then safety, operations, evaluation; commit per
checkpoint.

## Notes

- Mark a task `[x]` only after its verification ran and passed.
- `real_runtime` skipped = "not run". Human-judged metrics = "not run" until reviewed.
- Never edit the real S-CORE sources; hostile content lives only in synthetic fixtures.
