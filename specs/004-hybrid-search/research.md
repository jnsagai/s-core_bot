# Research: F004 Evidence Search and Exact-ID Navigation

Probes ran on the reference workstation on 2026-09-28 against the real active snapshot
`20260928T140548Z-7c6a05b3` (5 658 chunks, 4 336 entities, 768-dim vectors) and the local Ollama
0.34.0 runtime. Probe scripts were throwaway (scratchpad); the numbers are recorded here.

## R1. Identity of requirement IDs in the real corpus (affects FR-002, FR-003)

**Measured**: 2 168 need IDs occur twice. Each git-source need also exists as an export entity
from the associated `needs-export` source (`score-platform` ↔ `score-platform-needs`,
`score-process` ↔ `score-process-needs`). The only non-alphanumeric characters in real IDs are `_`
and `-` (e.g. `std_req__aspice_40__SWE-5-BP2`). Dotted IDs such as `MLE.3.BP1` do not occur in
these sources but are allowed by the parser, so fixtures cover them.

**Decision**: an unfiltered lookup returns all matches, ordered `pinned` before `unverified`, then
by source ID, then by key (spec FR-003, amended during planning with this evidence). An export copy
is unverified by definition (F002 A-014), so ranking the git-revision record first is not an
invented preference between authoritative sources. In search, when an exact token hits several
entities, each entity's first chunk is placed first in that same order. Export entities have no
chunks (F003 A-020), so their result line uses the entity record and marks `evidence: none
(export record)`.

**Alias rule (FR-002)**: `alias(id) = casefold(id)` with every run of `[-._\s]+` replaced by `_`,
and leading/trailing `_` stripped. The per-snapshot alias index (≈ 4 k entries) is built in
memory on first use and cached with the snapshot handle. The immutable F003 corpus has no alias
column, and none is needed.

## R2. Keyword retrieval: safe FTS5 queries and ranking (FR-007, FR-008)

**Decision**: tokenize the query on whitespace. Drop tokens with no letter or digit. Quote each
remaining token as an FTS5 string (`"` doubled) and join them with `OR`. This is literal matching
with no operators, prefixes, `NEAR` or column filters, and unicode61 with tokenchars `_-.` keeps
IDs whole. Rank with `bm25(chunks_fts, 1.0, 0.5, 2.0)` (text, heading path, need IDs; ID-column
hits weigh more). Filters are applied **in the same SQL statement** via a join on `chunks` (`WHERE
chunks_fts MATCH ? AND c.source_id IN (…) AND c.kind IN (…) ORDER BY bm25 … LIMIT 30`), so ranking
runs only over the filtered set (RET-002). A query with no usable tokens returns no keyword
candidates (not an error).
At most the first 64 distinct tokens become terms (a 4 000-character query could otherwise produce
hundreds of OR terms). The response notes `query_terms_truncated` when the cap applies. The query
itself is never truncated for exact matching.

**Measured**: p95 14 ms over 50 real queries (OR-of-terms, limit 30).

**Alternatives**: passing user text as an FTS expression was rejected (injection of operators,
syntax errors → 500s). AND-of-terms was rejected (natural-language questions rarely have every word
in one chunk); bm25 over OR still rewards chunks matching more terms.

## R3. Semantic retrieval (FR-012, FR-014)

**Query convention**: nomic-embed-text expects `search_query: ` for queries, pairing with F003's
`search_document: `. Measured on 4 real questions: the same top chunk with and without the prefix,
and cosine rose by 0.014–0.051 with it. **Decision**: prefix `search_query: `, with `truncate:
false`. An estimated query length over `embedding_max_input_tokens` skips semantic retrieval
(`query_too_long_for_embedding`).

**Search**: the pinned snapshot's float32 matrix is memory-mapped (F003 handle). There is one
float32 matrix–vector product; filter masks come from per-snapshot `source_id`/`kind` arrays
(row-aligned, loaded once per snapshot), and filtered-out rows are set to `-inf` before selection
(filter before rank). Top 30 via `argpartition`, then a stable sort by (−score, row). **Measured**:
cosine over 5 658 × 768 p95 19 ms (cold memmap included); query embedding p95 176 ms (warm model).

**Semantic status (FR-014, clarification Q3)**: `SnapshotValidator.semantic_status()` from F003
(model lock + runtime identity via `/api/tags` + `/api/show`, never an embedding). The result is
cached per snapshot for 30 s, and the cache is invalidated when a query embedding fails. Reasons
map to `snapshot_lexical_only` (absent), `embedding_identity_mismatch` (disabled),
`embedding_runtime_unavailable` (unverified or query-embed failure).

**Alternatives**: an ANN index was rejected (ADR-004: exact cosine is fine at this scale, 19 ms).

## R4. Fusion, dedup, caps, tie-breaks (FR-009, FR-010, RET-008)

**Decision** (`fusion_version: 1`):
1. Exact hits: entities matched by query tokens (verbatim first, then alias), in query order, then
   R1 ordering. Their first chunk (lowest ordinal carrying the key) goes to the top. Exact hits count
   toward the limit and the per-document cap.
2. Keyword and semantic lists (each ≤ 30) are fused with RRF: `Σ 1/(k + rank)`, `k = 60`, with
   ranks starting at 1.
3. Sort by (−rrf, document_key, ordinal) for deterministic ties.
4. Walk in order: skip a chunk already emitted, or whose `(source_id, content_hash)` was already
   emitted (dedup within a source; identical text in another source stays), or whose document
   already has `max_per_document` (default 3) results. Stop at `limit`.
5. `matched_by` collects every path that produced the chunk (`exact`/`alias`, `keyword`,
   `semantic`). `ranking_value` is the RRF sum (exact hits: null) and is documented as a relative
   ordering value only.

The final count and candidate sizes come from configuration (`retrieval.*`). New settings are
`max_per_document: 3`, `excerpt_characters: 1200`, `max_concurrent_searches: 4` and `max_limit: 20`.

## R5. Snapshot binding in the server (FR-013, OPS-002)

**Decision**: `SearchService` resolves the snapshot once per request (explicit ID or active
pointer), pins it through F003 `FileSnapshotStore.pin()`, and runs every path on that handle. The
handle is closed in `finally`. The alias index, filter arrays and the memmap are cached per snapshot
ID in a small LRU (2 snapshots). Each request still takes its own pin, so retention can never delete
an in-use snapshot, and a cached object for a snapshot that no longer exists is dropped when pinning
fails. SQLite connections are per request (`check_same_thread` safety; the file is immutable).
Queryable states: `active`, `validated`, `retired` (clarification Q1).

## R6. HTTP surface and bounds (FR-016, FR-018)

**Decision**: new FastAPI routes under `/api/v1` (sync `def` handlers run in Starlette's threadpool):

| Route | Purpose |
| --- | --- |
| `POST /api/v1/search` | search (body: `query`, `snapshot_id?`, `limit?`, `sources?`, `kinds?`) |
| `GET /api/v1/entities?id=…&snapshot_id=…&source_id=…` | exact/alias lookup |
| `GET /api/v1/relationships?key=…&snapshot_id=…&direction=out\|in\|both&limit&offset` | relationships |
| `GET /api/v1/snapshots` | queryable snapshots |
| `GET /api/v1/sources?snapshot_id=…` | sources of one snapshot |
| `GET /api/v1/citations/{snapshot_id}/{chunk_id}` | one chunk's stored text + provenance |

**Identifier validation (checklist CHK006)**: `snapshot_id` must match
`^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$` and `chunk_id` must be 64 lowercase hex characters. Both are
checked at the API/CLI edge **and** in `FileSnapshotStore.pin()` before any filesystem path is
built. F003's pin created `data/pins/<id>.pin` before the catalog check, which is safe for F003's
catalog-derived IDs but would allow a path like `../../x` from a request. Entity `id`/`key`
parameters are limited to 256 characters. Request models use `extra="forbid"`, bounded strings (query ≤ `limits.question_characters`) and a
filter allowlist validated against the pinned snapshot (unknown value → 422 listing allowed values).
Concurrency: a `threading.BoundedSemaphore(max_concurrent_searches)` acquired non-blocking in a
dependency → 429 `SEARCH_BUSY` (`retryable: true`). Deadline: the query-embedding timeout is
`min(index.embedding_timeout_seconds, limits.request_deadline_seconds)`. A timeout degrades to
lexical rather than failing, because lexical is cheap; if the whole request still exceeds the
deadline → 504. The existing F001 guard already rejects foreign `Origin` and `Sec-Fetch-Site:
cross-site` for every route, and the access log is body-free (verified in `api/guard.py`,
`api/logging.py`). Error envelope reuses F001's, with added `retryable`.

## R7. Readiness (FR-015)

**Decision**: `search` becomes available when the corpus probe says `compatible`. The F003
`not_implemented` reason for search is removed. `chat` keeps `not_implemented` (F005). If the active
snapshot's cached semantic status is not `enabled`, search stays available but carries the reason
`semantic_unavailable`, which is visible degradation (LOC-006). Readiness never embeds.

## R8. Evaluation (FR-019–FR-022)

**Case file** `eval/retrieval-dev.yaml` (repo path per master spec §14): `schema_version: 1`,
`review_status: "unreviewed (agent-authored)"`, `written_against: {source_id: revision}`, and cases
with `id`, `category` (`onboarding_build`, `architecture_interfaces`, `process_work_products`,
`requirements_templates`), `question`, `expected: [[locator, …], …]` (each inner list is one
evidence group, where any listed locator satisfies it). Locator = `{source_id, path}` with optional
`line_start/line_end` (overlap), or `{entity_key}`. Cases are written by reading the pinned sources
directly, never by running the search system, to avoid circular gold labels. **Recall@10 for a case
= satisfied groups / groups, macro-averaged; by-category averages with counts.**

**Exact-ID suite**: every distinct `need_id` in the snapshot → lookup → the first result's key is
the expected one (the pinned entity when a pinned one exists, per R1). Ambiguous duplicates within
one source are reported separately as `ambiguous_by_design`.

**Latency**: 5 warm-up queries, then ≥ 50 timed queries (the case questions, cycled) per mode
(keyword-only forced, and hybrid). The report gives p50 and p95, plus hardware (`diagnostics/
hardware.py`), runtime version and model digests, warm flag and snapshot ID. Wall-clock time is
measured in-process (service call), which excludes HTTP overhead; the report says so.

## R9. Excerpts and untrusted text (RET-004, constitution IV)

Excerpt = stored chunk display text (already normalized plain text), cut at the last whitespace
before 1 200 characters, `truncated: true`. No HTML, no link resolution. JSON is the only
rendering. The CLI prints plain text. The CLI and API never print the synthetic embedding input.

## Resolved unknowns

| Unknown | Resolution |
| --- | --- |
| Duplicate IDs in the real corpus | R1: all git needs duplicated by exports → pinned first |
| Safe keyword query construction | R2: quoted OR terms, filters in the same statement |
| Query prefix | R3: `search_query: ` (measured) |
| Latency feasibility | keyword 14 ms, embed 176 ms, cosine 19 ms p95 → far under 500 ms / 2 s |
| Concurrency and deadline | R6 |
| Evaluation format | R8 |
