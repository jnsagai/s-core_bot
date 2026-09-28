# Feature Specification: F003 Immutable Snapshots and Local Embedding Index

**Feature Branch**: `003-snapshot-index`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "F003 from docs/PROJECT_SPEC.md §16: chunking, SQLite schema/FTS
population, local embeddings, vector matrix manifest, staging/validation/activation, update/delete
semantics, embedding reuse, rollback, bundle import/export, schema compatibility. Acceptance:
interrupted builds preserve active corpus; digest mismatch is rejected; duplicate builds yield
identical logical chunk records; deleted/renamed sources update correctly; import/export verifies
hashes; active requests survive activation."

**Master requirements covered**: SRC-009, SRC-010, SRC-011 (F003 part), RET-007, OPS-002,
OPS-003 (primary); LOC-003 (build is a separate preparation step, never a download), LOC-006
(lexical-only snapshots when embeddings are unavailable), SRC-012 (redistribution of bundles),
master spec §6.4, §6.5, §9.2 (supporting). Acceptance tests AT-07, AT-08, AT-12 (store level),
AT-13, AT-16.

**Input from F002**: the source lock and `NormalizationService` output (documents, blocks,
entities with resolved links, coverage report). F003 never re-acquires sources.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build a validated, self-describing snapshot from the source lock (Priority: P1)

A maintainer runs one build command against the source lock. The build normalizes the locked
sources, cuts the documents into retrieval chunks that respect sections and requirement records,
stores documents, requirement records, relationships, chunks and a keyword index, computes local
embeddings (reusing earlier vectors when nothing relevant changed), writes manifests with
checksums, and validates everything — all in a staging area. Only a fully validated result is
published as a new snapshot; the snapshot users are currently served is never touched by a build.

**Why this priority**: search and answers (F004, F005) consume snapshots; without a trustworthy,
reproducible snapshot there is nothing to search.

**Independent Test**: from a fixture lock, build twice and compare chunk records; interrupt a build
at each stage and confirm the active snapshot and catalog are unchanged; build with the embedding
runtime unavailable with and without the lexical-only flag.

**Acceptance Scenarios**:

1. **Given** a lock with all required sources `ok`, **When** the build runs, **Then** a snapshot in
   state `validated` exists with a manifest recording the lock hash, every source revision, the
   processing and chunker versions, the token-count method, the embedding identity, file checksums,
   counts and the coverage summary.
2. **Given** the same lock and configuration, **When** the build runs twice, **Then** both
   snapshots contain byte-identical chunk records with identical chunk IDs.
3. **Given** a requirement record whose body fits the chunk budget, **When** chunked, **Then** it is
   exactly one chunk carrying its entity key; a longer one is split into ordered continuation chunks
   that all carry the key, and no text is dropped.
4. **Given** a table longer than the chunk budget, **When** chunked, **Then** every piece repeats the
   header row(s) and records which source rows it contains.
5. **Given** a second build where most documents are unchanged, **When** embeddings are computed,
   **Then** vectors for unchanged embedding inputs are reused from a retained snapshot with an
   identical embedding identity, and only changed inputs are sent to the embedding runtime.
6. **Given** the build is killed at any stage (normalizing, chunking, writing, embedding,
   validating, publishing), **When** anything is served afterwards, **Then** the previously active
   snapshot and the catalog's active pointer are unchanged, and the next build removes the orphaned
   staging data and records the interrupted build as `failed`.
7. **Given** the embedding runtime or model is unavailable, **When** the build runs without the
   lexical-only flag, **Then** it fails clearly; **with** the flag it produces a snapshot whose
   manifest states `semantic: absent`, which remains fully usable for keyword search.
8. **Given** a source file deleted or renamed between two locks, **When** the new snapshot is built,
   **Then** the old path is absent from it (and a renamed file appears under its new path), while
   the older snapshot still contains the old content.

---

### User Story 2 - Activate, pin, roll back, and retain snapshots safely (Priority: P2)

The maintainer lists snapshots, activates a validated one in a single atomic step, and can roll
back to the previous one. A reader that started on a snapshot keeps using that exact snapshot
(metadata, text and vectors) even if another snapshot is activated meanwhile, and old snapshots are
only removed when no reader uses them. The diagnostic and readiness checks recognise a compatible
installed corpus.

**Why this priority**: UJ-05 "update without interruption" — updates must never break or mix what
is being served.

**Independent Test**: activate A, pin A, activate B, confirm the pinned reader still reads A and
that retention does not delete A until the pin is released; roll back; corrupt a catalog schema.

**Acceptance Scenarios**:

1. **Given** a `validated` snapshot, **When** it is activated, **Then** it becomes `active` and the
   previously active one becomes `retired` in one transaction; a `failed` or `building` snapshot
   can never be activated.
2. **Given** a reader pinned to snapshot A, **When** snapshot B is activated, **Then** every read
   through that pin still returns A's data, and A's files are not deleted while the pin exists.
3. **Given** more snapshots than the retention count (default: active + previous), **When**
   retention runs after an activation, **Then** the oldest unpinned retired snapshots are removed,
   together with acquired source revisions no retained snapshot references; pinned ones are kept.
4. **Given** an active snapshot and a previous one, **When** rollback runs, **Then** the previous
   snapshot is active again and the other is `retired`.
5. **Given** a catalog or corpus whose schema version is newer than this release supports, **When**
   it is opened, **Then** it is refused with a clear message and not partially read.
6. **Given** an active, validated snapshot, **When** `doctor` or the readiness endpoint runs,
   **Then** the corpus is reported `compatible`, while `search` stays unavailable with reason
   `not_implemented` until F004 provides search.

---

### User Story 3 - Validate and move snapshots as verified bundles (Priority: P3)

The maintainer validates a snapshot on demand, exports it as a single bundle file, inspects a bundle
without importing it, and imports it on another prepared machine, where every hash and the schema
are verified before the snapshot is registered (never automatically activated).

**Why this priority**: relocatable data (G-05) and restore (OPS-003); needed before portable
releases (F009) but not for local search.

**Independent Test**: export → inspect → import into a fresh data directory → identical chunk and
entity identities; tampered, path-escaping and oversized bundles are refused; a snapshot containing
documents that require license review is not exported without an explicit acknowledgement.

**Acceptance Scenarios**:

1. **Given** a snapshot whose embedding manifest records a model digest different from the
   currently installed embedding model, **When** it is validated, **Then** semantic search is
   reported disabled for it with reindex guidance, and lexical data is still reported valid.
2. **Given** an exported bundle, **When** it is imported on a fresh data directory, **Then** the
   imported snapshot's manifest, chunk IDs, entity keys and file hashes equal the original's and it
   is registered as `validated`.
3. **Given** a bundle with a modified file, an entry escaping the extraction directory, a link, or
   a size above the cap, **When** it is imported, **Then** it is rejected and nothing is registered.
4. **Given** a snapshot containing documents whose license requires review (e.g. the
   CC-BY-SA-4.0 files observed in F002), **When** export runs without an explicit acknowledgement,
   **Then** it is refused, naming the files; with an acknowledgement and reason, the reason is
   recorded in the bundle manifest.

---

### Edge Cases

- Lock with a required source `failed` or missing on disk → build fails before chunking; nothing
  published; message names the source.
- Optional export source failed → snapshot still builds; manifest lists it as a coverage limitation.
- A document with zero chunkable text (only dynamic views or excluded raw content) → no chunks,
  counted in the manifest; not an error.
- A single paragraph or code block larger than the chunk budget → split, never truncated; code is
  split only at line boundaries.
- A chunk whose embedding input would exceed the embedding context bound under the conservative
  estimate → split further; if still impossible (one enormous line), the build fails naming it.
- Two sources contain identical text → two chunks with distinct attribution (same content hash,
  different chunk IDs).
- Embedding runtime returns a vector of unexpected dimension or a non-finite value → build fails.
- Disk full while writing → build fails in staging; active untouched.
- Activating the already-active snapshot → no change, success.
- Rollback with no previous snapshot → clear error, exit 1.
- A second build started while one is running → refused (single ingestion writer lock).
- Bundle from a newer schema version → refused at inspect and import.

## Requirements *(mandatory)*

### Functional Requirements

**Chunking (master spec §6.4)**

- **FR-001** (SRC-010): Chunks MUST follow structure: each requirement record (need) is one chunk
  unless it exceeds the budget; prose is grouped per heading path and never crosses a section
  boundary; tables, code/literal and diagram blocks form their own chunks; dynamic views and
  excluded raw content contribute no text.
- **FR-002**: Prose chunks MUST target 350–700 estimated tokens; a paragraph larger than the maximum
  is split at sentence boundaries with 50–100 tokens of overlap; code is split only at line
  boundaries with a continuation index; split tables repeat their header rows and record their row
  indices. Content is never truncated.
- **FR-003**: Token counts MUST use a documented, conservative estimate when the runtime tokenizer
  is unavailable, recorded in the manifest; every embedding input MUST fit the embedding model's
  context bound under that estimate (verified by an overflow test).
- **FR-004** (SRC-004, SRC-010): Each chunk MUST record a stable chunk ID (derived from the chunker
  version, document key, ordinal and content hash), document key, source ID, path, origin path,
  heading path, kind, display text (the verbatim normalized text — no synthetic prefix), the
  separately stored embedding input (synthetic context prefix: title, heading path, requirement IDs,
  source type), line span, entity keys, token estimate, content hash and embedding-input hash.
- **FR-005** (SRC-010): Identical lock, parser profile and chunker configuration MUST yield identical
  chunk records and IDs.

**Index files (master spec §9.2)**

- **FR-006**: Each snapshot MUST contain a corpus database holding documents, entities (export
  entities flagged `unverified`), relations (one row per link item with its resolution), chunks and
  a full-text keyword index over chunk text, heading path and requirement IDs; its schema version is
  recorded; SQLite extension loading is never enabled.
- **FR-007** (RET-007): Embeddings MUST come only from the configured local embedding model; vectors
  are L2-normalized float32, stored row-aligned in `embeddings.f32` with an embedding manifest
  recording provider, model tag, model digest, dimension, preprocessing revision, normalization,
  row count, file SHA-256 and the row→chunk map. The runtime MUST NOT truncate inputs silently.
- **FR-008**: A stored vector MUST be reused only when both the embedding-input hash and the full
  embedding identity match a vector in a retained snapshot.
- **FR-009** (LOC-006): If the embedding runtime or model is unavailable, the build MUST fail unless
  the operator explicitly requests a lexical-only snapshot, whose manifest then states
  `semantic: absent`.
- **FR-010** (SRC-011): The snapshot manifest MUST record snapshot ID, schema version, creation time,
  lock SHA-256, per-source revision map, processing hash, chunker version, token-count method,
  embedding identity (or absent), SHA-256 of every snapshot file, counts, the coverage summary with
  limitations, and the documents that require license review.

**Lifecycle (master spec §6.5)**

- **FR-011** (OPS-002, SRC-009): Snapshots MUST move through `building` → `validated` → `active` →
  `retired` (or `failed`), recorded in a catalog database. Builds write only to
  `data/staging/build-<job>/` and are moved into `data/snapshots/<id>/` only after validation.
  A failed or interrupted build MUST leave the active snapshot and the active pointer unchanged;
  orphaned staging data and `building` entries are recovered (removed / marked `failed`) by the
  next build. Only one build may run at a time.
- **FR-012**: Activation MUST require: every required lock source `ok`, zero integrity failures, and
  a coverage report; optional-source failures are recorded as coverage limitations.
- **FR-013** (OPS-002): Activation and rollback MUST each be a single atomic catalog transaction;
  activating the active snapshot is a no-op; rollback re-activates the previous snapshot.
- **FR-014** (OPS-002): A reader MUST be able to pin a snapshot for its lifetime; a pinned reader
  keeps reading that snapshot's metadata, corpus and vectors across activations; retention MUST
  never delete a pinned snapshot.
- **FR-015**: After an activation, retention MUST keep the active and previous snapshots (count
  configurable, minimum 2), delete older unpinned retired snapshots, and delete acquired source
  revisions and git caches no retained snapshot or current lock references.
- **FR-016** (RET-007): Validation MUST recompute file checksums, verify schema version, full-text
  index integrity, vector file shape (rows × dimension × 4 bytes), finite unit-norm vectors, and
  compare the embedding identity with the currently installed embedding model; a mismatch disables
  semantic use of that snapshot with reindex guidance instead of being silently accepted.
- **FR-017**: A catalog, corpus or bundle whose schema version is newer than supported MUST be
  refused with a clear message and never partially read.

**Bundles (OPS-003, SRC-012)**

- **FR-018**: Export MUST write one bundle file containing the snapshot's files and a bundle manifest
  with every file's SHA-256; it MUST refuse snapshots containing documents that require license
  review unless the operator provides an explicit acknowledgement with a reason, which is recorded
  in the bundle manifest.
- **FR-019**: Inspect MUST show a bundle's identity, schema, counts, embedding identity and license
  notes without importing it.
- **FR-020**: Import MUST extract only regular files within the target directory (no absolute paths,
  `..`, links or device entries; size caps), verify every hash and the schema before registering,
  and register the snapshot as `validated` — never active.

**Integration and commands**

- **FR-021**: The F001 corpus probe MUST report `compatible` when an active snapshot with a
  supported schema exists; readiness MUST keep `search` unavailable with reason `not_implemented`
  until F004; `doctor` guidance MUST reference the new commands.
- **FR-022** (LOC-003): The CLI MUST provide `index build`, `index validate`, `snapshots list`,
  `snapshots activate`, `snapshots rollback`, `bundle export`, `bundle inspect` and `bundle import`
  (master spec §10.2), with exit codes `0`/`1`/`2`. None of them downloads anything; the only
  network use is the loopback embedding runtime during `index build` and `index validate`.

### Key Entities

- **Chunk**: retrieval unit (FR-004).
- **CorpusSnapshot**: ID, state, manifest, directory, timestamps; catalog row (master spec §9.1).
- **SnapshotManifest**, **EmbeddingManifest**: per FR-007, FR-010.
- **EmbeddingIdentity**: provider, model tag, model digest, dimension, preprocessing revision,
  normalization.
- **Catalog**: snapshot rows, active pointer, build jobs.
- **Pin**: a reader's hold on one snapshot.
- **Bundle / BundleManifest**: exported snapshot plus hashes and license acknowledgement.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A full build of both initial sources completes in under 15 minutes on the reference
  workstation (including embeddings); a rebuild with unchanged sources completes in under 2 minutes
  thanks to embedding reuse.
- **SC-002**: Two builds from the same lock and configuration produce identical chunk records and
  IDs (100 %).
- **SC-003**: 100 % of embedding inputs in the real build fit the embedding context bound under the
  conservative estimate.
- **SC-004**: Interrupting a build at each of its stages leaves the active snapshot and pointer
  unchanged in 100 % of injected cases.
- **SC-005**: 100 % of embedding-identity mismatches (digest, dimension, preprocessing revision)
  are reported and disable semantic use rather than being accepted.
- **SC-006**: Export → import on a fresh data directory reproduces identical file hashes, chunk IDs
  and entity keys (100 %).
- **SC-007**: Files deleted or renamed between two locks are absent from (or renamed in) the new
  snapshot and still present in the old one.
- **SC-008**: A reader pinned during an activation observes only its original snapshot and blocks
  deletion of it (100 % of test cases).

## Assumptions

- The embedding model is the configured `nomic-embed-text` served by the local Ollama runtime
  (installed and locked in F001); its context bound, dimension and prompt conventions are verified
  against the real runtime during research, not assumed.
- Search, ranking and answers are F004/F005; F003 stores what they need and proves it is valid.
- One build at a time on one machine (master spec: single ingestion writer).

## Out of Scope

Query-time retrieval and ranking (F004), answer generation (F005), UI (F006), comparison (F007),
evaluation (F008), containers (F009), public hosting (F010), vector databases.
