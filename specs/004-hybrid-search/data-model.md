# Data Model: F004 Evidence Search and Exact-ID Navigation

Frozen Pydantic records in `src/score_docs_assistant/domain/retrieval.py`, independent of SQLite,
NumPy, FastAPI and Ollama (constitution VI). Records are built from a pinned F003 snapshot and never
persisted, except evaluation reports (JSON files under `data/reports/`).

## SearchRequest

| Field | Type | Rules |
| --- | --- | --- |
| `query` | str | 1 ≤ stripped length ≤ `limits.question_characters` (4 000) |
| `snapshot_id` | str \| None | None → active snapshot; must match `^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$`; state must be active/validated/retired |
| `limit` | int | 1 ≤ limit ≤ `retrieval.max_limit` (20); default `retrieval.evidence_chunks` (8) |
| `sources` | list[str] | each must be a source ID in the snapshot manifest; empty = all |
| `kinds` | list[ChunkKind] | subset of `prose, need, table, code, literal, diagram`; empty = all |

`extra="forbid"` so unknown fields (URLs, model names, options) are rejected.

## EvidenceResult

| Field | Type | Notes |
| --- | --- | --- |
| `rank` | int | 1-based |
| `chunk_id`, `snapshot_id`, `source_id`, `revision` | str | provenance |
| `revision_status` | `pinned` \| `unverified` | from the manifest's source entry |
| `path`, `origin_path` | str | |
| `heading_path` | list[str] | |
| `line_start`, `line_end` | int \| None | |
| `kind` | ChunkKind | |
| `entity_keys` | list[str] | |
| `excerpt` | str | display text, ≤ 1 200 chars, cut at whitespace |
| `truncated` | bool | |
| `matched_by` | list[`exact`\|`alias`\|`keyword`\|`semantic`] | sorted, unique |
| `ranking_value` | float \| None | RRF sum; null for exact hits. Schema description: "relative ordering value within this response; not a probability, confidence or measure of correctness" |

## SearchResponse

`schema_version: 1`, `snapshot_id`, `status: ok | no_results`, `mode: hybrid | lexical`,
`degraded: DegradedInfo | None` (`reason` ∈ `snapshot_lexical_only`, `embedding_identity_mismatch`,
`embedding_runtime_unavailable`, `query_too_long_for_embedding`; `detail`; `guidance: list[str]`),
`semantic_status` (the F003 status used), `results: list[EvidenceResult]`, `exact_matches:
list[EntitySummary]` (the entities that exact/alias matched, including export-only ones without
chunks), `warnings: list[str]`, `timings_ms: {exact, keyword, embedding, semantic, fusion,
total}`, `retrieval: {fusion_version, lexical_candidates, semantic_candidates, fusion_constant,
max_per_document}`.

## EntityRecord (lookup)

`key`, `need_id`, `match: exact | alias`, `type`, `title`, `status: str | None` (from options),
`source_id`, `revision`, `revision_status`, `path`, `line_start`, `line_end`, `origin`, `options:
dict[str, str]`, `excerpt: str | None` (first chunk with the key; None for export records),
`chunk_id: str | None`, `truncated`. **EntitySummary** = `key`, `need_id`, `match`, `source_id`,
`revision_status`, `title`.

## LookupResponse

`snapshot_id`, `query`, `status: ok | no_match`, `entities: list[EntityRecord]` (ordered per spec
FR-003: pinned → unverified, then source ID, then key).

## Relationship / RelationshipsResponse

Relationship: `direction: out | in`, `from_key`, `via` (option or `role:<name>`), `target_id`,
`qualifier`, `resolution` (`resolved|ambiguous|unresolved|malformed`), `resolved_keys`, `raw`.
Response: `snapshot_id`, `key`, `outgoing_total`, `incoming_total`, `items` (bounded by `limit` ≤ 200,
`offset`), ordered `out` before `in`, then by (`via`, `target_id`, `from_key`, relation id). Incoming
= relation rows whose `target_id` equals the entity's `need_id` and whose `resolved_keys` contain the
entity key.

## SnapshotSummary / SourceSummary

SnapshotSummary: `snapshot_id`, `state`, `active: bool`, `created_at`, `semantic: present|absent`,
`semantic_status` (cached), `chunks`, `documents`, `sources: list[source_id]`, `limitations:
list[str]`. SourceSummary: `source_id`, `kind`, `revision`, `revision_status`, `required`, `status`,
`license_review: list[path]`.

## CitationRecord

`snapshot_id`, `chunk_id`, `source_id`, `revision`, `revision_status`, `path`, `origin_path`,
`heading_path`, `line_start`, `line_end`, `kind`, `entity_keys`, `text` (full stored display text),
`continuation`.

## Evaluation records (`retrieval/evaluation.py`)

- **Locator**: `source_id` + `path` (+ optional `line_start`, `line_end`) **or** `entity_key`.
  A result satisfies a path locator when source and path are equal and, if lines are given, the
  line ranges overlap. It satisfies an entity locator when the key is in `entity_keys`.
- **RetrievalCase**: `id` (unique), `category` (4 values), `question`, `expected:
  list[list[Locator]]` (≥ 1 group, each ≥ 1 locator), `notes`.
- **CaseFile**: `schema_version: 1`, `review_status`, `written_against: dict[source_id, revision]`,
  `cases`. Warning when `written_against` differs from the snapshot's revisions.
- **CaseResult**: `id`, `category`, `group_ranks: list[int | None]`, `recall_at_10`, `mode`.
- **RetrievalReport**: `snapshot_id`, `case_file_sha256`, `review_status`, `configuration`,
  `cases`, `macro_recall_at_10`, `by_category: {category: {cases, recall}}`, `generated_at`,
  `labels: ["development measurement", "not release evidence"]` when unreviewed.
- **ExactIdReport**: `snapshot_id`, `ids_checked`, `correct_first`, `failures: list[{need_id,
  expected, got}]`, `ambiguous_by_design: list[need_id]`.
- **LatencyReport**: `snapshot_id`, `queries_per_mode`, `warmup`, `modes: {lexical: {p50_ms,
  p95_ms}, hybrid: {…}}`, `embedding_warm`, `environment: {cpu, ram, gpu, os, runtime_version,
  embedding_digest}`, `measured_in: "service call (excludes HTTP)"`.

## Configuration additions (`config/schema.py`, `RetrievalConfig`)

```yaml
retrieval:
  lexical_candidates: 30      # existing
  semantic_candidates: 30     # existing
  evidence_chunks: 8          # existing (default limit)
  fusion_constant: 60         # existing
  max_limit: 20               # new, ≥ evidence_chunks
  max_per_document: 3         # new, ≥ 1
  excerpt_characters: 1200    # new, 200..10000
  max_concurrent_searches: 4  # new, 1..64
  semantic_status_ttl_seconds: 30  # new, 0..3600
```

## Errors (`domain/errors.py`)

`SearchError(code, message, http_status, retryable)` with codes: `QUERY_INVALID` (422),
`FILTER_INVALID` (422), `SNAPSHOT_NOT_FOUND` (404), `NO_ACTIVE_SNAPSHOT` (409),
`SNAPSHOT_INCOMPATIBLE` (409), `CHUNK_NOT_FOUND` (404), `ENTITY_NOT_FOUND` (404, relationships
only), `SEARCH_BUSY` (429, retryable), `DEADLINE_EXCEEDED` (504, retryable). CLI: 422 → exit 2,
others → exit 1. F003 `SnapshotError`s raised while pinning are mapped to these.
