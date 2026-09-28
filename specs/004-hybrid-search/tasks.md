---

description: "Task list for F004 Evidence Search and Exact-ID Navigation"
---

# Tasks: F004 Evidence Search and Exact-ID Navigation

**Input**: Design documents from `specs/004-hybrid-search/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md,
checklists/security.md

**Tests**: MANDATORY (constitution VII). Write tests first and confirm they fail. Deterministic
tests use fixture snapshots built with `FakeEmbeddingProvider` (mocked); `real_runtime` tests count
as "not run" when skipped. Synthetic fixtures carry `SYNTHETIC — not S-CORE guidance`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on incomplete tasks)
- **[Story]**: US1 (exact lookup), US2 (search), US3 (evaluation)
- Paths are repository-relative (package root `src/score_docs_assistant/`)

---

## Phase 1: Setup

- [x] T001 [P] Create `src/score_docs_assistant/retrieval/__init__.py` and empty modules `query.py`, `exact.py`, `lexical.py`, `semantic.py`, `fusion.py`, `status.py`, `service.py`, `evaluation.py` (docstring only), plus `src/score_docs_assistant/domain/retrieval.py`, `api/search_routes.py`, `cli/search.py`, `cli/evaluate.py`
- [x] T002 [P] Create `eval/` with a `README.md` stating that case files are development measurements until reviewed (F008), per master spec §13.2

---

## Phase 2: Foundational (blocking)

### Tests

- [x] T003 [P] Write `tests/unit/test_retrieval_config.py`: new `RetrievalConfig` fields and defaults (data-model), `max_limit ≥ evidence_chunks`, bounds on `max_per_document`, `excerpt_characters` (200..10000), `max_concurrent_searches` (1..64), `semantic_status_ttl_seconds` (0..3600); `config/local.yaml` still loads
- [x] T004 [P] Write `tests/unit/test_query.py`: whitespace tokenization; ID tokens strip trailing `.,;:!?)`; `alias()` rule (casefold, `[-._\s]+` → `_`, trim); FTS expression quotes every token and doubles `"`; tokens without letters/digits dropped; 64-term cap with flag; operator words (`AND`, `NEAR(`, `*`, `-x`, `col:val`) stay literal; excerpt cut at whitespace ≤ limit with `truncated` flag (FR-002, FR-007, research R2, R9)
- [x] T005 [P] Write `tests/unit/test_identifiers.py`: snapshot-ID and chunk-ID patterns accept real IDs and reject `../x`, `a/b`, empty, overlong, uppercase hex; `FileSnapshotStore.pin()` rejects an invalid ID **before** creating any file under `data/pins/` (checklist CHK006)
- [x] T006 [P] Extend `tests/helpers/snapshot_env.py` with `search_sources()`: alpha (RST: dotted ID `MLE.3.BP1` in a `std_req`, `feat_req__alpha__short` linking to `feat_req__alpha__long` and to an unknown ID, three chunks' worth of prose in one document for the per-document cap, a table, code), beta (same need ID `std_req__dup__one` as alpha, a paragraph identical to one in alpha), and an export source `alpha-needs` duplicating alpha's IDs; extend `tests/helpers/fake_embedding.py` with `embed_query()` and a `query_vectors` override map so tests can dictate semantic ranking; create `tests/helpers/search.py` building a validated + active fixture snapshot and a `SearchService`

### Implementation

- [x] T007 Add the new `RetrievalConfig` fields in `src/score_docs_assistant/config/schema.py` — makes T003 pass
- [x] T008 [P] Implement `retrieval/query.py` (tokenize, id_tokens, alias, fts_expression, excerpt, identifier patterns) — makes T004 pass
- [x] T009 [P] Add `SearchError` to `domain/errors.py` and the records of data-model.md to `domain/retrieval.py`; add ID validation to `storage/snapshot_store.py` `pin()` before the pin file is created — makes T005 pass
- [x] T010 Add `embed_query()` to the `EmbeddingProvider` protocol (`models/runtime.py`) and `OllamaEmbeddingProvider` (`search_query: ` prefix, `truncate: false`, too-long → `EMBEDDING_INPUT_TOO_LONG`), with a unit test in `tests/unit/test_ollama_embed.py` (FR-012, research R3)

**Checkpoint**: unit tests, mypy, ruff green.

---

## Phase 3: User Story 1 — Exact lookup and relationships (P1) 🎯 MVP

**Independent Test**: every fixture ID is found first; alias/duplicate/export/no-match behave as
specified; relationships equal stored rows.

- [x] T011 [P] [US1] Write `tests/unit/test_exact.py`: verbatim hit labelled `exact` with FR-004 fields and excerpt; `MLE.3.BP1` verbatim; `mle-3-bp1` → `alias` showing original; duplicate `std_req__dup__one` → both, ordered by source; git vs export copy → pinned first, export `unverified` with no excerpt; `alpha:ID` restricts; unknown `zzz:ID` prefix → no match; unknown ID → `no_match`; no fuzzy results (FR-001–FR-004, research R1)
- [x] T012 [P] [US1] Write `tests/unit/test_relationships.py`: outgoing links with via/target/qualifier/resolution/resolved keys exactly as stored (including the unresolved link); incoming links of `feat_req__alpha__long` include `feat_req__alpha__short`; totals and `limit`/`offset` bounds (≤ 200); unknown key → `ENTITY_NOT_FOUND` (FR-005)
- [x] T013 [US1] Implement `retrieval/exact.py` (per-snapshot entity + alias index, lookup ordering, entity excerpt from first chunk, relationships out/in with pagination) — makes T011, T012 pass
- [x] T014 [US1] Implement `SearchService.lookup()` and `.relationships()` in `retrieval/service.py` (resolve + pin snapshot per call, queryable states, errors) with `tests/integration/test_search_service.py::test_lookup_*` (FR-013)
- [x] T015 [US1] Implement `lookup` in `cli/search.py` and register it; write `tests/contract/test_cli_search.py::test_lookup_*` (help line, text/JSON, `--relationships`, exit codes 0/1/2) (FR-017)

**Checkpoint**: gate green; real `lookup feat_req__baselibs__json --relationships` recorded.

---

## Phase 4: User Story 2 — Search (P2)

**Independent Test**: deterministic ranked lists; filters before rank; degraded lexical mode with
reasons; no cross-snapshot content.

### Tests

- [ ] T016 [P] [US2] Write `tests/unit/test_lexical.py`: filters in the ranking statement (a source whose best match is weaker still yields up to 30 candidates when filtered to it); kind filter; operator-only queries return no error; ID column weighting ranks an ID match above prose mentions (FR-007, FR-008)
- [ ] T017 [P] [US2] Write `tests/unit/test_semantic.py`: top-k by cosine with dictated query vectors; filter mask applied before selection (filtered-out best rows never returned, k filled from allowed rows); stable ties by row (FR-008, research R3)
- [ ] T018 [P] [US2] Write `tests/unit/test_fusion.py`: RRF values; exact hits first in query order; tie-break by (document_key, ordinal); dedup `(source_id, content_hash)` within a source but not across sources; per-document cap; limit; `matched_by` union; exact hits have `ranking_value` null (FR-009, FR-010, research R4)
- [ ] T019 [P] [US2] Write `tests/unit/test_status_cache.py`: TTL reuse, expiry, invalidation after failed query embedding, per-snapshot keys (FR-014, clarification Q3)
- [ ] T020 [US2] Write `tests/integration/test_search_service.py::test_search_*`: hybrid default; an ID in a question ranks first; degraded reasons for lexical-only snapshot, identity mismatch (with reindex guidance), runtime unreachable, embed failure mid-request, too-long query; `--lexical` forcing; no generation model needed; repeated requests identical (SC-006); validated and retired snapshots searchable, failed/deleted → `SNAPSHOT_NOT_FOUND`; no active → `NO_ACTIVE_SNAPSHOT`; unknown filter value → `FILTER_INVALID` listing allowed values; excerpt ≤ 1 200 and never the embedding input (FR-006–FR-015)
- [ ] T021 [US2] Write `tests/integration/test_isolation.py`: two snapshots with disjoint text; searching A never returns B's chunks/entities/excerpts; activation of B while a request on A is paused inside the service (hook) still yields only A; results carry A's snapshot ID (FR-013, SC-002, AT-03, AT-12)
- [ ] T022 [US2] Write `tests/contract/test_search_api.py`: all six routes happy paths; 422 for unknown fields, empty/too-long query, bad filter, invalid snapshot/chunk ID format; 404 unknown snapshot/chunk/entity; 409 no active snapshot; 429 when the semaphore is exhausted (threads); `Origin: https://evil.example` → 403; access log line has no query text; no response schema contains `score`, `confidence` or `probability`; readiness search available with `semantic_unavailable` when degraded and chat still `not_implemented` (FR-011, FR-015, FR-016, FR-018, SC-007)
- [ ] T023 [US2] Extend `tests/contract/test_cli_search.py` with `search` cases: help line, text and `--json` output, `--source/--kind/--limit/--lexical`, degraded warning line, exit codes (FR-017)

### Implementation

- [ ] T024 [P] [US2] Implement `retrieval/lexical.py` — makes T016 pass
- [ ] T025 [P] [US2] Implement `retrieval/semantic.py` (per-snapshot filter arrays from the corpus, masked top-k over the memmap) — makes T017 pass
- [ ] T026 [P] [US2] Implement `retrieval/fusion.py` — makes T018 pass
- [ ] T027 [P] [US2] Implement `retrieval/status.py` — makes T019 pass
- [ ] T028 [US2] Implement `SearchService.search()`, `.snapshots()`, `.sources()`, `.citation()`, per-snapshot LRU caches, concurrency gate and deadline handling in `retrieval/service.py` — makes T020, T021 pass
- [ ] T029 [US2] Implement `api/search_routes.py`, register it in `api/app.py` with a `SearchService`, wire `cli/serve.py`; update `readiness.py` and `domain/readiness.py` (`SEMANTIC_UNAVAILABLE`, search available when compatible) — makes T022 pass
- [ ] T030 [US2] Implement `search` in `cli/search.py` — makes T023 pass
- [ ] T031 [US2] Add a `real_runtime` test in `tests/integration/test_real_runtime.py`: hybrid search over the fixture snapshot built with real embeddings returns `mode: hybrid` and semantic matches (FR-012)

**Checkpoint**: gate green; quickstart C, D on the real snapshot recorded.

---

## Phase 5: User Story 3 — Evaluation (P3)

- [ ] T032 [P] [US3] Write `tests/unit/test_evaluation.py`: case-file schema (unknown keys, duplicate IDs, empty groups, bad lines → error); locator matching (path, line overlap, entity key); recall@10 per case, macro and by category with counts; unreviewed label; `written_against` mismatch warning; exact-ID suite counts failures and `ambiguous_by_design`; latency percentiles from injected timings; hybrid "not run" without runtime (FR-019–FR-021)
- [ ] T033 [US3] Implement `retrieval/evaluation.py` — makes T032 pass
- [ ] T034 [US3] Implement `eval retrieval | exact-ids | latency` in `cli/evaluate.py` with `tests/contract/test_cli_eval.py` (help lines, exit codes, report files, malformed case file exit 2)
- [ ] T035 [US3] Author `eval/retrieval-dev.yaml`: ≥ 30 cases over the four categories (≥ 6 each) with gold locations read from the pinned sources (`data/sources/<id>/<rev>/…`), `review_status: "unreviewed (agent-authored)"`, `written_against` revisions; validate it with `eval retrieval` loading (FR-022)

**Checkpoint**: gate green; quickstart E, F on the real snapshot recorded.

---

## Phase 6: Polish

- [ ] T036 [P] Update `README.md` and `CLAUDE.md` with `search`, `lookup`, `eval` and the new API routes; re-run documented commands
- [ ] T037 [P] Update `docs/BACKLOG.md`, `docs/TRACEABILITY.md` (RET-001–RET-004, RET-008, LOC-006, RET-005/RET-007 search parts) and `docs/ASSUMPTIONS.md` (A-025 pinned-before-unverified ordering; A-026 64-term cap; A-027 export records returned without evidence chunks)
- [ ] T038 Run the full gate plus `SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -m real_runtime`; record commands and results in `specs/004-hybrid-search/verification.md`
- [ ] T039 Walk quickstart A–F on the workstation; record exact-ID results, recall@10 by category (labelled development measurement), p50/p95 per mode with environment, and deviations in `verification.md`

---

## Dependencies & Execution Order

Setup → Foundational → US1 → US2 → US3 → Polish. US2 reuses US1's exact index for exact hits in
search; US3 needs US1 and US2. Within a story: tests first → modules → service → interfaces.

### Parallel Opportunities

T001–T002; T003–T006; T008–T009; T011–T012; T016–T019; T024–T027; T036–T037.

## Implementation Strategy

MVP = Phases 1–3 (exact lookup works with no models at all). Then search, evaluation, polish; one
commit per checkpoint.

## Notes

- Mark a task `[x]` only after its verification ran and passed.
- `real_runtime` skipped = "not run".
- Gold evaluation locations come from reading the sources, never from this system's output.
