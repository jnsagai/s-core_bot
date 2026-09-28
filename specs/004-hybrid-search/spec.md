# Feature Specification: F004 Evidence Search and Exact-ID Navigation

**Feature Branch**: `004-hybrid-search`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "F004 from docs/PROJECT_SPEC.md §16: Evidence search and exact-ID
navigation. Scope: keyword/vector/exact retrieval over a pinned F003 snapshot, filter-before-rank
behavior, reciprocal-rank fusion, deduplication, evidence API (HTTP) and CLI, degraded lexical mode
when semantic search is unavailable, relationship lookup for requirement records, initial retrieval
evaluation. Acceptance: exact-ID suite passes; scope filters cannot leak other snapshots/sources;
search functions without generation; retrieval recall and performance are reported against
initial cases."

**Master requirements covered**: RET-001, RET-002, RET-003, RET-004, RET-008, LOC-006 (primary);
RET-005 (single-snapshot binding for search), RET-007 (semantic use only for validated indexes, at
query time), SRC-004 (namespaced IDs), OPS-002 (request pinning), UJ-03, master spec §7.1, §10.1,
§10.2 (`search`), §13.3 (evidence recall@10, exact-ID retrieval, snapshot isolation), §13.4
(lexical and hybrid latency). Acceptance tests AT-02 (search without generation), AT-03 (store and
search level), AT-04, AT-08 (query time), AT-12 (search level).

**Input from F003**: activated or validated snapshots (corpus with full-text index, vectors with
embedding identity, manifest), `SnapshotStore` pins, the validator's semantic status, and the
catalog. F004 never builds or modifies snapshots.

## Clarifications

### Session 2026-09-28

Resolved autonomously by the agent (agent review, not an approval) from `docs/PROJECT_SPEC.md` and
F001–F003 precedent at the project owner's request ("be fully autonomous"); see
`docs/ASSUMPTIONS.md` A-024. The owner may override any answer.

- Q: Which snapshot states can be searched? → A: `active`, `validated` and `retired` (CLI and API);
  never `building`, `failed` or `deleted`. Without a snapshot ID, the active snapshot is used.
  Basis: master spec §6.5 ("a staging snapshot may be queried for evaluation by an operator"),
  UJ-05 evaluate-before-activate.
- Q: Which query tokens count as IDs for exact matching inside a free-text search? → A: every
  whitespace-separated token, with trailing sentence punctuation (`.,;:!?)`) stripped, that exists
  in the snapshot's entity table verbatim or through the FR-002 alias. There is no pattern-based
  guessing; all exact hits rank first, in query order. Basis: RET-003, §7.1 "exact unique-ID lookup
  bypasses ambiguity".
- Q: How often is a snapshot's semantic status re-checked while serving? → A: it is cached per
  snapshot for at most 30 seconds and re-checked immediately after any failed query embedding;
  each response reports the status it used. Basis: RET-007, AT-08; avoids a runtime round trip per
  query.
- Q: How long may an excerpt in a search result be? → A: at most 1 200 characters, cut at a word
  boundary and marked `truncated: true`; the full stored text is available from the citation
  endpoint. Basis: RET-004 "readable excerpts", RET-008 bounded results.
- Q: How many search/lookup requests may run at once? → A: at most 4 concurrently (configurable);
  further requests are rejected immediately with HTTP 429 (`retryable: true`), and the CLI is
  unaffected. Basis: constitution Technology & Security Constraints ("concurrency … bounded in
  every profile"), master spec §10.1 status codes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Look up an exact requirement ID and navigate its relationships (Priority: P1)

A developer or safety engineer types a known identifier such as `feat_req__com__interfaces` or
`MLE.3.BP1`. They get that exact record first, with its title, type, status, source, revision,
file and line location, a readable excerpt, and the relationships the source actually states
(outgoing links with their resolution, plus records that link to it). When the same ID exists in
several sources, every match is shown with its source namespace instead of one being picked
silently. When nothing matches exactly, they are told so and can fall back to a normal search.

**Why this priority**: exact lookup is the most reliable way to reach evidence (UJ-03). It works
without any model and is the foundation that search and answers build on.

**Independent Test**: for every requirement ID in a fixture snapshot, lookup returns it first;
punctuation- and case-variant queries behave as specified; duplicate IDs across sources return
all namespaced matches; relationships match the stored link records exactly.

**Acceptance Scenarios**:

1. **Given** a snapshot containing `feat_req__alpha__short` in source `alpha`, **When** the user
   looks up `feat_req__alpha__short`, **Then** the first result is that entity with source,
   revision, path, line span and excerpt, and it is marked as an exact match.
2. **Given** an ID containing dots, dashes or underscores (e.g. `MLE.3.BP1`), **When** it is looked
   up verbatim, **Then** it matches exactly; a different punctuation or case spelling matches only
   through a normalized alias and is labelled as such, and the original spelling is shown.
3. **Given** the same need ID in two sources, **When** it is looked up without a source filter,
   **Then** both entities are returned, each with its namespaced key and no preference invented; a
   namespaced query (`source:ID`) returns only that source's entity.
4. **Given** an entity with outgoing links, **When** its relationships are requested, **Then**
   every stored link appears with its option name, target ID, qualifier and resolution
   (resolved, ambiguous, unresolved, malformed), and resolved targets are navigable; incoming links
   (records that point to it) are listed too; no relationship is inferred that the source does
   not state.
5. **Given** an ID that exists only in a `needs-export` source, **When** it is looked up, **Then** it
   is returned labelled `unverified` (not bound to a git revision).
6. **Given** an ID that does not exist, **When** it is looked up, **Then** the result says "no exact
   match" rather than returning a near miss as if it were exact.

---

### User Story 2 - Search the documentation and get ranked, provenance-rich evidence (Priority: P2)

A user types a natural-language question or keywords, optionally restricted to certain sources or
kinds of content. They get a short, bounded, ranked list of evidence excerpts from one selected
snapshot. Each excerpt shows the source, revision, file path, section, line location and why it
matched (exact ID, keyword, meaning, or several). Results work even when the local language model
for answers is not running, and keyword results still work when the embedding model is missing or
does not match the snapshot. In that case the degraded mode is stated plainly.

**Why this priority**: search is the first useful end-to-end capability (LOC-006) and is what F005
answers will ground on.

**Independent Test**: on fixture snapshots, searches return deterministic ranked lists; filters
exclude non-matching sources before ranking; semantic-unavailable conditions yield keyword results
with an explicit warning; another snapshot's content never appears.

**Acceptance Scenarios**:

1. **Given** an active snapshot with semantic search enabled, **When** the user searches, **Then**
   they receive at most the requested number of results (default 8, maximum 20), fused from exact,
   keyword and semantic matches, each with excerpt, provenance, matched-by labels and a rank. A
   ranking score, if shown, is labelled as a relative ranking value, not a probability of
   correctness.
2. **Given** a query containing a unique requirement ID, **When** searched, **Then** that entity's
   evidence is ranked first regardless of semantic similarity.
3. **Given** a source or content-kind filter, **When** searched, **Then** only matching evidence is
   considered for ranking, so the full result count comes from the filtered set rather than being
   a truncated remainder of an unfiltered top list.
4. **Given** two snapshots with different content, **When** the user searches snapshot A, **Then**
   no result, excerpt or relationship from snapshot B appears, even if B is active or was activated
   during the request.
5. **Given** the embedding runtime is unreachable, or the snapshot's embedding identity does not
   match the installed model, or the snapshot is lexical-only, **When** the user searches, **Then**
   results come from exact and keyword retrieval only and the response states `degraded: lexical`
   with the reason and, for identity mismatch, reindex guidance.
6. **Given** the generation model is not installed or not running, **When** the user searches,
   **Then** search works normally (generation is never used by search).
7. **Given** many matching chunks from one document or duplicate text in several places, **When**
   searched, **Then** results are deduplicated (identical text within one source shown once) and at
   most a bounded number come from any one document, while distinct source attribution is kept.
8. **Given** the same query, snapshot and filters, **When** searched twice, **Then** the ranked
   result list is identical (deterministic tie-breaks).

---

### User Story 3 - Measure retrieval quality and speed against an initial case set (Priority: P3)

A maintainer runs a retrieval evaluation against a pinned snapshot and a versioned case file. They
get a report of exact-ID accuracy over every requirement ID in the corpus, evidence recall at 10 on
a set of question cases with expected evidence locations, and search latency percentiles for
keyword-only and hybrid modes, with the hardware and model identities recorded. Cases written by
the agent are labelled unreviewed and are not release evidence.

**Why this priority**: the backlog's acceptance requires recall and performance to be reported.
The release-grade, expert-reviewed evaluation is F008.

**Independent Test**: running the evaluation on a fixture snapshot with fixture cases produces the
expected metrics deterministically; missing gold evidence, unknown snapshot and malformed case
files are reported clearly.

**Acceptance Scenarios**:

1. **Given** a snapshot and a case file, **When** the evaluation runs, **Then** the report lists per
   case the rank at which each expected evidence group was found (or "not found in top 10"), the
   macro-averaged recall@10 overall and by category, with case counts, and the case file's hash
   and review status.
2. **Given** a snapshot, **When** the exact-ID suite runs, **Then** every requirement ID stored in the
   snapshot is looked up and the report states how many returned the correct entity first, listing
   any failures.
3. **Given** a snapshot, **When** the latency measurement runs with at least 50 queries after warm-up,
   **Then** p50 and p95 are reported separately for keyword-only and hybrid search, together with
   hardware, runtime and model identities, and whether the embedding model was warm.

---

### Edge Cases

- Empty or whitespace-only query → rejected as a usage error (CLI exit 2, HTTP 422).
- Query longer than the configured question limit → rejected, not truncated.
- Query consisting only of punctuation or full-text operators (`"`, `*`, `AND`, `NEAR(`, `-`, `:`)
  → treated literally; never interpreted as a full-text query expression; no server error.
- ID-like query with trailing punctuation (e.g. `feat_req__x.` at the end of a sentence) → exact
  lookup tries the verbatim token and the token without trailing sentence punctuation.
- Filter naming a source or content kind that does not exist in the snapshot → validation error
  listing allowed values, not an empty success.
- No active snapshot and no snapshot given → clear "no active snapshot" error (CLI exit 1, HTTP 409
  with guidance to build/activate).
- Snapshot ID unknown, deleted, failed or building → 404 / exit 1.
- More than the allowed concurrent searches → HTTP 429 with `retryable: true`; nothing queued.
- Snapshot pinned by a request is retired or deleted-by-retention attempt during the request → the
  request completes on its pinned snapshot (F003 pins).
- Query matches nothing → empty result list with status `no_results`, not an error.
- Embedding request for the query fails mid-request → keyword results returned with `degraded:
  lexical` rather than a failure.
- Very common query term matching thousands of chunks → bounded candidate sets; response time
  within budget.
- Entity with dozens of relationships → relationships returned complete but bounded per page with a
  total count.
- Namespaced query with an unknown source prefix → treated as plain text search, and exact lookup
  reports no match.
- Duplicate need IDs within one source (`…#2` keys from F002) → both returned, distinguishable.
- Result excerpts containing markup or links → returned as plain text only; no rendering and no
  fetching of links.

## Requirements *(mandatory)*

### Functional Requirements

**Exact-ID lookup (RET-003, SRC-004, UJ-03)**

- **FR-001**: Users MUST be able to look up a requirement record by its ID, verbatim, via CLI and
  HTTP. Verbatim matches preserve case and punctuation and are labelled `exact`.
- **FR-002**: When no verbatim match exists, lookup MUST try one documented normalized alias form
  (case-folded, with `-`, `.` and `_` sequences treated as equivalent separators). Alias matches
  MUST be labelled `alias` and show the original spelling. Lookup never returns fuzzy or
  similarity-based matches.
- **FR-003**: When several entities share an ID (across sources, or duplicates within a source),
  lookup MUST return all of them with their namespaced keys, ordered deterministically: records
  bound to a pinned git revision before `unverified` export copies, then by source ID, then by key.
  No other preference is invented between sources. A `source_id:ID` query MUST restrict to that
  source. (Plan research R1: in the real corpus every git-source need also exists in its
  `needs-export` copy, so an unfiltered lookup always has two matches.)
- **FR-004**: Each lookup result MUST include the namespaced key, original ID, type, title, status
  (if stated), source ID, revision, revision status (`pinned` or `unverified`), path, line span, the
  entity's options as stored, and a readable excerpt from the entity's chunk(s).
- **FR-005**: Relationship lookup MUST return an entity's outgoing links (option name, target ID,
  qualifier, resolution, resolved keys) and incoming links (entities whose resolved links point to
  it), exactly as stored in the snapshot, bounded with total counts. No relationship may be
  inferred.

**Search (RET-001, RET-002, RET-004, RET-008)**

- **FR-006**: Search MUST combine three paths over one snapshot: exact-ID matches for query tokens
  (whitespace-separated, trailing `.,;:!?)]"'` and leading `(["'` stripped) that exist in the snapshot's entity table
  verbatim or by FR-002 alias, keyword retrieval over chunk text, heading path and IDs, and semantic
  retrieval over the snapshot's vectors when semantic use is enabled.
- **FR-007**: Keyword queries MUST be built safely from the user's words: every term is treated as
  literal text, full-text syntax in the query is never executed, and punctuation-bearing IDs stay
  searchable.
- **FR-008**: Source and content-kind filters MUST restrict the candidate set before ranking in
  every path (keyword, semantic, exact), so that results come from the filtered set only.
- **FR-009**: Keyword and semantic candidate lists MUST be bounded (defaults 30 each, from
  configuration) and fused by reciprocal-rank fusion (default constant 60). Entities matched
  exactly by a unique ID MUST be ranked first. Ties MUST be broken deterministically by
  document and chunk identity.
- **FR-010**: Final results MUST be bounded (default 8, request maximum 20). They MUST be
  deduplicated by content within a source, keeping the best-ranked chunk, and capped per document
  (default 3). Distinct sources with identical text MUST remain distinct results.
- **FR-011**: Each result MUST contain the chunk ID, snapshot ID, source ID, revision, revision
  status, path, origin path, heading path, line span, content kind, entity keys, a readable
  plain-text excerpt (the stored display text, at most 1 200 characters cut at a word boundary and
  flagged `truncated`, never the synthetic embedding prefix), the matched-by labels (`exact`, `alias`, `keyword`, `semantic`) and the rank. Any numeric
  value MUST be labelled a relative ranking value, and no field may call it a probability,
  confidence or correctness.
- **FR-012**: The query embedding for semantic retrieval MUST come only from the configured local
  embedding model, using the model's query convention, and MUST NOT be truncated silently. A query
  that exceeds the embedding context bound skips semantic retrieval with a stated reason.

**Snapshot binding and degraded modes (RET-005, RET-007, LOC-006, OPS-002)**

- **FR-013**: Every search, lookup, relationship and evidence request MUST be bound to exactly one
  snapshot in state `active`, `validated` or `retired`: the one named in the request, or the active
  snapshot resolved once at request start. It
  MUST hold that snapshot's pin for its whole duration, and MUST return the snapshot ID in the
  response. Content from any other snapshot MUST NOT appear.
- **FR-014**: Semantic retrieval MUST be used only when the snapshot's semantic status is `enabled`
  (vectors present and embedding identity matching the model lock and the installed runtime model).
  Otherwise search MUST run in keyword mode and report `degraded: lexical` with a reason code
  (`snapshot_lexical_only`, `embedding_identity_mismatch` with reindex guidance,
  `embedding_runtime_unavailable`, `query_too_long_for_embedding`). Semantic status MAY be cached
  per snapshot for at most 30 seconds and MUST be re-checked immediately after a failed query
  embedding; each response reports the status it used.
- **FR-015**: Search and lookup MUST NOT depend on the generation model. Their availability MUST be
  reported independently of chat availability, and readiness MUST mark search available (possibly
  degraded) when a compatible active snapshot exists, replacing F003's `not_implemented` reason for
  search.

**Interfaces (§10.1, §10.2)**

- **FR-016**: The HTTP API MUST provide: `POST /api/v1/search` (query, optional snapshot ID, limit,
  allowlisted source/kind filters), exact lookup and relationship endpoints for entities, `GET
  /api/v1/snapshots` (queryable snapshots with state, semantic status and coverage summary), `GET
  /api/v1/sources?snapshot_id=…` (sources, revisions, revision status, license notes) and `GET
  /api/v1/citations/{snapshot_id}/{chunk_id}` (the stored excerpt and provenance of one chunk).
  Unknown request fields, arbitrary URLs, model names and runtime options MUST be rejected. Errors
  use the F001 envelope with the status codes of master spec §10.1 (400/422 malformed, 404 unknown
  ID, 409 no compatible or active snapshot, 503 dependency unavailable, 504 deadline).
- **FR-017**: The CLI MUST provide `search "query" [--snapshot ID] [--source …] [--kind …] [--limit
  N] [--json]` and `lookup ID [--snapshot ID] [--relationships] [--json]`, with exit codes 0
  (results or explicit no-results), 1 (operational failure, no snapshot), 2 (usage error). Neither
  downloads anything; the only network use is the loopback embedding runtime for query embeddings.
- **FR-018**: Search and lookup requests MUST obey the configured request deadline and question
  length limit, MUST NOT log query text or result bodies, and MUST go through F001's Host/Origin
  protection. At most 4 search/lookup requests (configurable) run concurrently in the server;
  further ones are rejected at once with HTTP 429 (`retryable: true`). Search is a costly request and MUST be protected against cross-origin calls like
  other costly endpoints.

**Evaluation (§13.3, §13.4)**

- **FR-019**: The CLI MUST provide `eval retrieval --snapshot ID --cases FILE` that reports, per case
  and in aggregate (macro average, by category, with counts), the rank of each expected evidence
  group and recall@10, together with the case file hash, the case review status, the snapshot ID
  and the retrieval configuration.
- **FR-020**: The CLI MUST provide an exact-ID suite over every requirement ID in a snapshot that
  reports the number and list of IDs whose correct entity is not first.
- **FR-021**: The CLI MUST provide a latency measurement (≥ 50 queries after warm-up) reporting p50
  and p95 separately for keyword-only and hybrid search, with hardware, runtime and model identities
  and warm/cold state.
- **FR-022**: An initial case file of at least 30 question cases with expected evidence locations,
  drawn from the pinned S-CORE sources and spread over onboarding/build, architecture/interfaces,
  process/work products and requirements/templates, MUST be committed with review status
  `unreviewed (agent-authored)`. Its results MUST be reported as development measurements, never as
  release evidence.

### Key Entities

- **SearchRequest**: query text, optional snapshot ID, limit, source filter, kind filter.
- **EvidenceResult**: one ranked chunk with provenance, excerpt, matched-by labels and rank.
- **SearchResponse**: snapshot ID, status (`ok`, `no_results`), mode (`hybrid` or `degraded:
  lexical` with reason), results, warnings, timing.
- **EntityRecord**: a requirement record as returned by lookup (FR-004), with match kind
  (`exact`/`alias`).
- **Relationship**: outgoing or incoming link with option name, target, qualifier, resolution and
  resolved keys.
- **RetrievalCase**: case ID, category, question, expected evidence groups (each a set of acceptable
  source/path/line or entity locations), review status.
- **EvaluationReport**: per-case ranks, recall@10 aggregates, exact-ID results, latency percentiles,
  environment identity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100 % of requirement IDs stored in the real snapshot and in fixtures, exact lookup
  returns the correct entity first (duplicates: all namespaced matches returned, ordered
  deterministically).
- **SC-002**: Zero results from another snapshot or from a filtered-out source across the dedicated
  isolation and filter tests, including a snapshot activation during a request.
- **SC-003**: Search returns evidence with the generation model absent in 100 % of tests, and
  keyword results with an explicit degraded label whenever semantic search is unavailable.
- **SC-004**: On the reference workstation, keyword-only search p95 ≤ 500 ms and hybrid search p95
  ≤ 2 s with the embedding model warm, over ≥ 50 queries on the real snapshot. The measured values
  are reported, and a miss is recorded as a scoped decision, never hidden.
- **SC-005**: Evidence recall@10 on the initial case set is measured and reported with
  denominators by category. The master target (≥ 90 % on held-out, reviewed cases) is F008's
  release gate; F004 reports its development measurement without claiming it.
- **SC-006**: The same request returns an identical ranked list in 100 % of repeated runs.
- **SC-007**: No response field presents a ranking value as a probability or confidence (checked on
  every response schema).

## Assumptions

- Query embeddings use nomic-embed-text's documented `search_query: ` prefix, matching F003's
  `search_document: ` document prefix (to be confirmed against the real runtime during research).
- Defaults come from the existing configuration (`retrieval.lexical_candidates: 30`,
  `semantic_candidates: 30`, `fusion_constant: 60`, `evidence_chunks: 8`). A per-document cap
  (default 3) and a maximum excerpt length are added.
- One serving worker (master spec §9.2). Vectors of the pinned snapshot may be held in memory for
  exact cosine search. At ~5 700 × 768 floats (≈ 17 MB) no index structure is needed (ADR-004).
- Chat, answer generation, context budgets for prompts, neighbor expansion for answers and the UI
  are F005/F006. F004 returns evidence only.
- Agent-authored evaluation cases are allowed for development measurement. Expert review and the
  100-case frozen split are F008.

## Out of Scope

Answer generation and chat (F005), UI (F006), snapshot comparison (F007), release-grade evaluation
and thresholds (F008), containers (F009), public hosting (F010), new index structures or vector
databases, query rewriting with a language model, and cross-snapshot search.
