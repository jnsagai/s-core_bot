# Implementation Plan: F004 Evidence Search and Exact-ID Navigation

**Branch**: `004-hybrid-search` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-hybrid-search/spec.md`

## Summary

Add a `retrieval/` package that answers three questions over one pinned F003 snapshot:
exact/alias requirement-ID lookup with stored relationships, keyword search via safe quoted-term
FTS5 queries with filters inside the ranking statement, and semantic search via exact cosine over
the snapshot's memory-mapped vectors with filter masks. Keyword and semantic ranks are fused with
reciprocal-rank fusion behind exact hits, then deduplicated, capped per document and tie-broken
deterministically. The same `SearchService` backs the CLI (`search`, `lookup`, `eval …`) and new
`/api/v1` routes (search, entities, relationships, snapshots, sources, citations), with bounded
concurrency, deadlines, degraded lexical mode and readiness reporting search as available. Initial
evaluation adds an agent-authored, unreviewed case file plus exact-ID and latency reports.

## Technical Context

**Language/Version**: Python 3.12 (unchanged)

**Primary Dependencies**: no new packages. Uses stdlib `sqlite3` (FTS5), NumPy (F003), FastAPI/
Starlette (F001), PyYAML (`safe_load` for case files), F003 `FileSnapshotStore`,
`SnapshotValidator.semantic_status`, `OllamaEmbeddingProvider` (a query path is added).

**Storage**: read-only access to `data/snapshots/<id>/` through pins, and `data/catalog.sqlite`.
Evaluation reports go to `data/reports/`. The case file `eval/retrieval-dev.yaml` is committed.

**Testing**: pytest with the F001 socket guard. Fixture snapshots are built by the F003 test
helpers (`tests/helpers/snapshot_env.py`, extended with dotted IDs, duplicate IDs across sources,
an export source and relationship chains) using `FakeEmbeddingProvider`, extended with a
query-embedding path, so semantic ranking is testable. HTTP uses Starlette `TestClient`;
concurrency uses threads; `real_runtime` covers hybrid search against real Ollama.

**Target Platform**: Linux x86-64 (unchanged).

**Project Type**: single Python project, CLI + library + local HTTP service.

**Performance Goals**: keyword p95 ≤ 500 ms, hybrid p95 ≤ 2 s warm (SC-004). Measured probes:
keyword 14 ms, query embedding 176 ms, cosine 19 ms (research R2, R3).

**Constraints**: no generation model on the search path; loopback embedding only; no query text in
logs; single snapshot per request; bounded candidates, results, excerpts, relationships and
concurrency; deterministic ordering.

**Scale/Scope**: real snapshot with 5 658 chunks and 4 336 entities (2 168 IDs duplicated between git
and export sources); ≥ 30 initial cases.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Status | How this plan complies |
| --- | --- | --- |
| I. Local operation | PASS | Only the loopback embedding runtime is used, for query vectors; search works with no runtime at all (lexical). No downloads on the serve path. |
| II. Evidence precedes assertions | PASS | Results carry server-side provenance (snapshot, source, revision, path, lines) from stored records only. No model output is involved. |
| III. Snapshots explicit | PASS | One pinned snapshot per request, its ID in every response; semantic use only for a validated identity (FR-013, FR-014). |
| IV. Documentation untrusted | PASS | Quoted-literal FTS queries; excerpts returned as plain text; no link resolution or rendering; filters allowlisted. |
| V. Read-only assistance | PASS | Search/lookup are read-only; no tools or commands; F003 catalog untouched. |
| VI. Modular monolith | PASS | `retrieval/` package behind one service; domain records in `domain/retrieval.py`; no new services or index infrastructure (ADR-004 holds: exact cosine at 19 ms). |
| VII. Honest verification | PASS | Mocked vs real-runtime vs real-snapshot evidence separated; agent-authored cases labelled unreviewed, development-only; F008 owns release thresholds. |
| VIII. Privacy | PASS | Body-free access log (F001); service logs no query or result text; no telemetry. |
| IX. Spec-first | PASS | RET-001–004, RET-008, LOC-006 mapped; TRACEABILITY updated after implementation. |
| X. Public profile separate | PASS | Loopback bind and guard unchanged; new endpoints covered by the existing Host/Origin/cross-site guard; concurrency bounded. |
| XI. Licenses follow artifacts | PASS | Sources endpoint exposes license-review flags; excerpts keep source attribution. |
| XII. No implied authority | PASS | No confidence/probability fields; ranking value labelled relative ordering only. |

Post-design re-check: **PASS**. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/004-hybrid-search/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/ cli.md, http-api.md, eval-cases.md
├── checklists/ requirements.md (+ checklist phase)
├── tasks.md
└── verification.md
```

### Source Code (repository root)

```text
src/score_docs_assistant/
├── domain/retrieval.py          # SearchRequest, EvidenceResult, SearchResponse, EntityRecord,
│                                # Relationship, SnapshotSummary, SourceSummary, CitationRecord
├── domain/errors.py             # + SearchError (code, http_status, retryable)
├── domain/readiness.py          # + ReasonCode.SEMANTIC_UNAVAILABLE
├── config/schema.py             # RetrievalConfig: max_limit, max_per_document, excerpt_characters,
│                                # max_concurrent_searches, semantic_status_ttl_seconds
├── models/runtime.py            # EmbeddingProvider protocol: + embed_query
├── models/ollama_embed.py       # + embed_query() ("search_query: " prefix, truncate:false)
├── retrieval/
│   ├── __init__.py
│   ├── query.py                 # tokenize, ID tokens, alias(), FTS expression builder, excerpt()
│   ├── exact.py                 # per-snapshot entity/alias index; lookup(); relationships()
│   ├── lexical.py               # keyword candidates with filters in the ranking statement
│   ├── semantic.py              # per-snapshot filter arrays; top-k cosine over the memmap
│   ├── fusion.py                # exact-first + RRF + dedup + per-document cap + tie-breaks
│   ├── status.py                # SemanticStatusCache (TTL, invalidate on embed failure)
│   ├── service.py               # SearchService: resolve+pin snapshot, orchestrate, timings,
│   │                            # snapshots/sources/citations queries, concurrency gate
│   └── evaluation.py            # case-file loader, recall@10, exact-ID suite, latency
├── api/search_routes.py         # /api/v1 search, entities, relationships, snapshots, sources, citations
├── api/app.py                   # register search routes with a SearchService
├── readiness.py                 # search available when compatible; semantic_unavailable reason
├── cli/search.py                # `search`, `lookup`
├── cli/evaluate.py              # `eval retrieval | exact-ids | latency`
└── cli/serve.py                 # build the SearchService for the app
eval/retrieval-dev.yaml          # ≥ 30 agent-authored cases, review_status unreviewed
tests/
├── helpers/ snapshot_env.py (+ dotted/duplicate IDs, export source, relationships),
│            fake_embedding.py (+ embed_query), search.py (service factory over fixtures)
├── unit/ test_query.py, test_exact.py, test_lexical.py, test_semantic.py, test_fusion.py,
│         test_status_cache.py, test_retrieval_config.py, test_evaluation.py
├── contract/ test_cli_search.py, test_cli_eval.py, test_search_api.py
└── integration/ test_search_service.py, test_isolation.py, test_real_runtime.py (+ hybrid)
```

**Structure Decision**: follows master spec §14 (`retrieval/` for exact/lexical/vector search and
fusion). The service is the single entry point for CLI and API, so both share bounds and
behaviour.

## Key Design Decisions

1. **Exact first, never fuzzy** (R1): verbatim → alias; duplicates all returned, pinned before
   unverified.
2. **Filters inside ranking** (R2, R3): SQL `WHERE` inside the FTS statement; `-inf` mask before
   top-k.
3. **Literal keyword queries** (R2): quoted OR terms, so no user text is ever an FTS expression.
4. **One pin per request** (R5): per-snapshot caches are reused, but each request pins; no mixing.
5. **Degrade, don't fail** (R3, R6): any semantic problem yields lexical results plus an explicit
   reason; only malformed input, unknown IDs, busy or deadline produce errors.
6. **Deterministic** (R4): RRF with fixed constants, stable sort keys, no randomness.
7. **Evaluation honesty** (R8): gold labels from reading sources; unreviewed label enforced in the
   report.

## Verification Strategy

| Requirement | Verification (layer) |
| --- | --- |
| FR-001–FR-004, SC-001 | unit: lookup verbatim/alias/namespaced/duplicate/export/no-match on fixtures; integration: exact-ID suite over the fixture snapshot; real: `eval exact-ids` on the real snapshot = 100 % |
| FR-005 | unit: outgoing/incoming links equal the stored relation rows; unresolved/ambiguous kept; bounded pagination with totals |
| FR-006, FR-009 | unit: RRF math, exact-first, tie-break keys; integration: an ID in a question ranks first |
| FR-007 | unit: operator/quote/punctuation-only/`NEAR(`/`-`/`:` queries → no error, literal match |
| FR-008, SC-002 | integration: filters change the candidate set before ranking (a source with a weaker match still fills results); cross-snapshot isolation incl. activation mid-request |
| FR-010 | unit: dedup within source, distinct across sources, per-document cap, limit bounds |
| FR-011, SC-007 | contract: response schema fields; test that no response schema has `score`, `confidence` or `probability` keys; excerpt ≤ 1 200, no embedding prefix |
| FR-012 | unit: query prefix, `truncate:false`, too-long query skips semantic |
| FR-013 | integration: pinned handle for the whole request; snapshot ID in every response; retired/validated searchable, failed/deleted 404 |
| FR-014, SC-003 | integration: lexical-only snapshot, identity mismatch (reindex guidance), runtime down, embed failure → lexical + reason; cache TTL and invalidation |
| FR-015 | contract: readiness search available (+ `semantic_unavailable`), chat still `not_implemented`; search without a generation model |
| FR-016, FR-018 | contract: every route, 404/409/422/429/504, unknown fields rejected, cross-origin 403, body-free log, concurrency gate with threads |
| FR-017 | contract: CLI help lines, exit codes, `--json`, `--lexical` |
| FR-019–FR-021 | unit/contract: evaluation on fixture cases gives expected ranks/recall; malformed case file exit 2; latency report shape, hybrid "not run" without runtime |
| FR-022, SC-004, SC-005 | real: case file ≥ 30 cases committed; recall@10 and latency measured on the real snapshot and recorded in verification.md |
| SC-006 | integration: repeated identical requests give identical lists |

## Complexity Tracking

No constitution violations; section intentionally empty.
