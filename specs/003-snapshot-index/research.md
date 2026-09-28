# Research: F003 Immutable Snapshots and Local Embedding Index

All probes below were run on the reference workstation on 2026-09-28 against the real local
runtime (Ollama 0.34.0, `nomic-embed-text:latest` digest `0a109f42…e59f`, `qwen3:4b-instruct`
digest `0edcdef3…8ba0`, both matching `data/model-lock.json`) and the real F002 source lock
(`score-platform@e2373d8`, `score-process@66321fe`, two exports). Probe scripts were throwaway
(scratchpad); the numbers are recorded here so tasks can turn them into tests.

## R1. Embedding runtime facts (resolves spec assumption "verified against the real runtime")

**Measured**:

| Fact | Value | How observed |
| --- | --- | --- |
| Endpoint | `POST /api/embed` (`input` may be a list) | real calls |
| Dimension | 768 | `/api/show` `nomic-bert.embedding_length`; response vector length |
| Model context bound | **2048 tokens** (`nomic-bert.context_length`) | `/api/show`; the Modelfile's `num_ctx 8192` does **not** raise it |
| Default overflow behavior | **silent truncation** to 2048 tokens (HTTP 200, `prompt_eval_count: 2048`) | 3 000-word input |
| `truncate: false` | HTTP 400 `{"error":"the input length exceeds the context length"}` | same input, also with `num_ctx: 8192` |
| Output norm | ≈ 1.0 (already L2-normalized, float64 JSON) | `‖v‖ = 1.00000007` |
| Determinism | repeated call and batch-vs-single identical bit for bit (same machine) | max abs diff 0.0 |
| Throughput | ≈ 70 inputs/s at ~250 words, batch 16 or 64 (GPU) | 128 inputs |
| Token count feedback | `prompt_eval_count` = total tokens of the request | real calls |
| Model license | Apache-2.0 (`/api/show` `license`) | resolves `config/model-profiles.yaml` "to confirm" |
| Prompt template | `{{ .Prompt }}` (no automatic task prefix) | `/api/show` |

**Decision**: `OllamaEmbeddingProvider` always sends `truncate: false` (FR-007 "MUST NOT truncate
silently"); an HTTP 400 context-length error becomes `EmbeddingInputTooLong` naming the chunk and
fails the build. Vectors are re-normalized in float32 after receipt, and any non-finite value or
wrong dimension fails the build. Document inputs get the model's documented task prefix
`search_document: ` (queries in F004 will use `search_query: `); the prefix string is part of the
preprocessing revision. The context bound is read from `/api/show` at build time and recorded in
the embedding manifest. The build refuses to start if it is below the configured embedding input
cap (R2).

**Rationale**: silent truncation is the default, so leaving `truncate` unset would violate
FR-007. The runtime has no other overflow signal.

**Alternatives**: `/api/embeddings` (legacy, single input, no `truncate` flag) was rejected.
Trusting the returned norm was rejected because float64→float32 conversion needs re-normalization
anyway.

## R2. Conservative token estimate (FR-003, SC-003)

**Measured**: 150 random real paragraphs from both sources, plus 8 adversarial strings. For each
one, real token counts came from nomic (`/api/embed`) and from qwen (`/api/generate`, raw,
`num_predict: 1`).

- Characters per token, real text: nomic min 1.88 / median 3.62; qwen min 2.16 / median 4.76.
  A flat `chars / 2` rule therefore **under-counts** some real paragraphs (tables, need options).
- Candidate `pretoken-v1`: split on `[A-Za-z]+ | [0-9] | [^\sA-Za-z0-9]`, count
  `ceil(len/2)` per ASCII-letter run, one token per UTF-8 byte for every digit, punctuation or
  non-ASCII character, plus 2 special tokens. Against `max(nomic, qwen)` over 250 real paragraphs
  it never under-counted (min ratio 1.00 on punctuation- or digit-only strings, median 1.86). Its
  only under-count was synthetic consonant gibberish (`Zxqvbnm Qwrtpsdf…`, ratio 0.73), because
  WordPiece falls back to single characters there.
- `ceil(len/3)` and `ceil(len/4)` under-counted 2 and 10 real paragraphs respectively → rejected.

**Decision**: token-count method `pretoken-v1` (above), recorded in the manifest as
`token_count_method`. Budgets are expressed in `pretoken-v1` units. The estimate is conservative
for real documentation, but no cheap estimator is conservative against arbitrary adversarial
text. So the **hard guarantee** is R1's `truncate: false`: an input the runtime cannot fit fails
the build loudly, so a successful build proves that every input fit the real bound (SC-003).
Embedding input cap: **1 800** estimated tokens (configurable, must be < runtime context bound),
which leaves a 12 % margin under 2 048.

**Rationale**: the median over-estimate (≈1.9×) makes real prose chunks smaller than the nominal
350–700 (≈190–380 real qwen tokens). That is acceptable for retrieval granularity and keeps the
estimate honest. Evaluation in F008 may retune the budget (recorded change, new chunker version).

**Alternatives**: calling the runtime tokenizer for every candidate split was rejected: Ollama
0.34 has no tokenize endpoint, `prompt_eval_count` needs a full embedding call, and the build
would depend on the runtime even for lexical-only snapshots. Bundling a tokenizer library
(`tokenizers`) was rejected: it adds a native dependency plus model vocab files whose licenses
must be tracked, for a marginal gain.

## R3. Chunking algorithm (FR-001–FR-005)

**Decision** (chunker version `1`):

1. Walk each document's top-level blocks in order, carrying `heading_path`. Skip
   `dynamic_view`, `raw_excluded`, `section` (the title lives in `heading_path` and the
   embedding prefix) and empty-text blocks.
2. `need` block (has `entity_key`): its text plus its children's texts joined by blank lines
   form one chunk of kind `need`. If it exceeds `max_tokens` (700), it is split at child-block
   boundaries, then at sentence boundaries, into ordered continuation chunks. Every
   continuation carries the entity key and `continuation = i/n`.
3. `table`: kind `table`. Rows are accumulated up to `max_tokens`, and every piece repeats the
   header rows (`attrs.header_rows`) and records `row_start`/`row_end` (0-based body row
   indices).
4. `code` / `literal` / `diagram`: own chunk of that kind. If over `max_tokens`, it is split at
   line boundaries only, with `continuation = i/n`.
5. All other text-bearing kinds (paragraph, list, admonition, field/definition list, block
   quote, generic directive text, toctree captions, image alt) are **prose**. Consecutive prose
   blocks with the *same* `heading_path` are accumulated until adding the next would exceed
   `max_tokens`, so a section change always closes the chunk. A section smaller than
   `min_tokens` (350) stays a small chunk (never merged across sections).
6. A single prose block over `max_tokens` is split at sentence boundaries
   (`(?<=[.!?])\s+(?=[A-Z0-9"'(\[])`) into windows ≤ `max_tokens`, with the trailing whole
   sentences of the previous window (target 75, bounded 50–100 estimated tokens) repeated as
   overlap. A single sentence over `max_tokens` falls back to whitespace boundaries.
7. Oversize fallback: a single unsplittable unit (one code line, one table row, one
   whitespace-free token run) larger than `max_tokens` is allowed as its own chunk if its
   embedding input fits the 1 800 cap. Otherwise the build fails with `CHUNK_UNSPLITTABLE`,
   naming the source, path and line. Nothing is ever truncated.
8. Line span: `min(line_start)`–`max(line_end)` of contributing blocks (null if none known);
   `origin_path` from the first block (chunks never mix origin paths — an origin change closes
   the chunk).
9. Display text = the contributing normalized texts joined by `\n\n` (tables: rows rendered
   `a | b | c` per line, header first; code: verbatim lines). No synthetic text.
10. Embedding input = `search_document: ` + prefix + `\n\n` + display text. The prefix is
    `Title: <doc title>`, `Section: <heading path joined " > ">`, `IDs: <need IDs>` (from
    entity keys) and `Source: <source_id> (<format>)`. The prefix is capped at 160 estimated
    tokens by eliding middle heading-path items with `…` (it is synthetic, so shortening it is
    not truncating content).
11. `chunk_id = canonical_hash({chunker_version, document_key, ordinal, content_hash})` with
    `content_hash = sha256(display_text)` and `embedding_input_hash = sha256(embedding_input)`.
    The document key already binds source ID, path, raw bytes and processing hash (F002 R9).

The chunker configuration hash (`chunker_version`, `min/max/overlap`, `token_count_method`,
prefix template version) is recorded in the manifest. Changing it changes chunk IDs through
`chunker_version` bumps. The config values are also hashed so that tuning without a version bump
still yields a different `chunker_config_sha256` and prevents embedding reuse through the prefix
hash.

**Exports**: `needs-export` documents have no blocks (F002). They contribute entities and
relations (flagged `unverified`) but **no chunks**. The git-source need blocks carry the same
records with exact provenance, and chunking both would double every requirement in retrieval.
Recorded as a coverage note in the manifest.

**Alternatives**: fixed-size sliding windows were rejected (they cross sections and split
needs, violating FR-001). One chunk per block was rejected (thousands of tiny chunks with no
context).

## R4. Storage: corpus database (FR-006)

**Decision**: stdlib `sqlite3` (SQLite 3.53.1 here, `ENABLE_FTS5` compiled in, verified).
`corpus.sqlite` is written once in staging, with `PRAGMA user_version = 1` (corpus schema
version), `journal_mode=DELETE` (a single file after close, no `-wal` sidecar to checksum),
followed by `VACUUM` and close before hashing. FTS5 external-content table over `chunks`
(`text`, `heading_path`, `need_ids`) with `tokenize = "unicode61 remove_diacritics 2
tokenchars '_-.'"`, so IDs like `feat_req__baselibs__json` and `MLE.3.BP1` stay single tokens.
It is followed by `INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')` during
validation. Every connection to a corpus or catalog file applies SQLite's untrusted-database
hardening: `PRAGMA trusted_schema = OFF`, `PRAGMA cell_size_check = ON`, and
`setconfig(SQLITE_DBCONFIG_DEFENSIVE, True)` (Python 3.12 API). A corpus can arrive from a
bundle, so it is treated as untrusted until validated. Readers open `file:…?mode=ro&immutable=1` URIs (files never change once published,
and immutable skips locking). `enable_load_extension` is never called. Full schema in
[contracts/snapshot-files.md](contracts/snapshot-files.md).

**Alternatives**: WAL mode was rejected (sidecar files complicate checksums and immutability).
A single shared corpus DB with a snapshot column was rejected (violates snapshot immutability
and makes deletion hard).

## R5. Vector file (FR-007)

**Decision**: add **NumPy** (BSD-3-Clause, constitution baseline "NumPy exact cosine") as a
runtime dependency. `embeddings.f32` = raw little-endian float32, C-order, `rows × dim`, no
header. `embedding-manifest.json` records `rows`, `dimension`, `dtype: "<f4"`, `sha256`, and
`row_chunk_ids` (row i ↔ chunk ID). Readers use `numpy.fromfile` or `numpy.memmap(mode="r")`
after checking `size == rows × dim × 4`. Validation checks finiteness and |‖v‖ − 1| ≤ 1e-3 per
row. No pickle and no `.npy` object arrays (`allow_pickle` is never reached, because raw
`fromfile` is used).

**Alternatives**: `.npy` was rejected (a header format with a pickle escape hatch; raw plus
manifest is simpler to validate). A vector DB is forbidden by CLAUDE.md.

## R6. Embedding reuse (FR-008, SC-001)

**Decision**: before embedding, build a lookup `embedding_input_hash → (snapshot, row)` from
every retained snapshot (state `validated|active|retired`) whose embedding identity equals the
current identity exactly (all six fields). The build **pins** each snapshot it reads from (R8),
so retention cannot delete it mid-read. It reads only those rows (memmap), verifies each reused
vector is finite and unit-norm, and sends only the misses to the runtime in batches of 32.
A second build with unchanged sources therefore makes zero embedding requests.

**Alternatives**: a global embedding cache file outside snapshots was rejected: it adds a
second mutable store with its own consistency problem, while retained snapshots already hold
verified vectors.

## R7. Catalog and lifecycle (FR-011–FR-013, FR-017)

**Decision**: `data/catalog.sqlite` (WAL mode — mutable, many readers), `PRAGMA user_version =
1`. Tables `snapshots`, `active_pointer` (single row), `activation_history`, `build_jobs`
([contracts/catalog.md](contracts/catalog.md)). All mutations run in `BEGIN IMMEDIATE`
transactions. Build sequence:

1. Acquire `data/locks/ingest.lock` with `flock(LOCK_EX | LOCK_NB)`; if it is busy, exit 1 with
   "another build is running". Require free disk on `data_dir` ≥ `diagnostics.disk_margin_bytes`
   (existing F001 setting, default 2 GiB) plus the size of the newest retained snapshot, if any.
   Otherwise exit 1 with `DISK_INSUFFICIENT` before staging anything. A disk-full error later is
   still possible and is handled as a stage failure.
2. Recovery: every `build_jobs` row still `running` whose PID holds no lock (we hold the lock,
   so none can) → `failed` (`interrupted`); its snapshot row `building` → `failed`; remove
   `data/staging/build-*` and any `data/snapshots/<id>/` whose catalog row is `failed`.
3. Insert job (`running`) and snapshot row (`building`), commit.
4. Stages in `data/staging/build-<job>/`: normalize → chunk → write corpus → embed → write
   vectors + manifests + reports → validate (the same validator as `index validate`).
5. `fsync` files and the directory, `chmod` files 0444, `os.replace` staging dir →
   `data/snapshots/<id>/`, `fsync(data/snapshots)`.
6. One transaction: snapshot `building → validated`, store `manifest_sha256`, job `succeeded`.
7. Optional `--activate`: activation (below), still holding the ingest lock.

A crash at any point before step 6 leaves the active pointer untouched, because only step 6 and
activation write it; the next build's step 2 cleans up. Activation: re-hash every file listed in
the manifest, compare `manifest.json` against the catalog's `manifest_sha256` and check schema
versions; then one transaction: old active → `retired`, target → `active`, update
`active_pointer`, and append `activation_history(seq, snapshot_id, previous_id, kind)`. Rollback
target = `previous_id` of the latest history row, which must be `retired` and still on disk.
Rollback then appends its own history row, so a second rollback returns. Retention runs after a
committed activation.

Snapshot ID: `<UTC yyyymmddTHHMMSSZ>-<first 8 hex of job UUID>`. It sorts chronologically and
stays unique for duplicate builds (FR-005 concerns chunk records, not snapshot IDs).

**Alternatives**: a symlink `data/snapshots/current` swapped atomically was rejected: it adds
a second source of truth next to the catalog, and the spec puts the pointer in the catalog
transaction.

## R8. Cross-process pins (FR-014, SC-008)

**Decision**: per-snapshot pin file `data/pins/<snapshot_id>.pin`, held open with
`fcntl.flock(LOCK_SH)` by every reader (`SnapshotStore.pin(id)` → context manager / handle). The
kernel releases flock locks when the process exits for any reason, including SIGKILL, which is
exactly the clarified semantics. Retention: `flock(LOCK_EX | LOCK_NB)` on the pin file; on
`BlockingIOError` the snapshot is pinned and skipped. When the lock is acquired, it deletes the
snapshot directory while holding the exclusive lock, marks the row deleted, then removes the pin
file. Readers: resolve the ID → acquire the shared lock → re-check that the catalog row exists and
is not deleted, and that the directory exists (otherwise release and retry resolution once).
This closes the race between resolving and pinning. Active snapshots are never retention
candidates, so the race window only concerns a concurrent activation plus retention.

**Rationale**: the platform is Linux x86-64 (F001), and `flock` is POSIX-available and
crash-safe. Tests: a subprocess pins and the parent tries retention (skipped); the subprocess
is killed with SIGKILL and retention then deletes.

**Alternatives**: PID files plus liveness checks were rejected (PID reuse, and a crash leaves
stale files). Catalog rows with heartbeats were rejected (needs timeouts and is wrong under
suspend).

## R9. Validation (FR-016) and embedding identity (spec clarification Q2)

**Decision**: `SnapshotValidator.validate(dir) → ValidationReport` with separate `integrity`
checks (failures → exit 1) and a `semantic` status:

- Integrity: manifest parses and its schema version is supported; every listed file exists and
  matches its SHA-256; no unlisted files; `corpus.sqlite` `user_version` is supported;
  `PRAGMA integrity_check` returns `ok`; FTS `integrity-check`; counts equal the manifest; for
  semantic snapshots, file size = rows × dim × 4, all values finite, every row within 1e-3 of
  unit norm, `row_chunk_ids` equal the chunk IDs in corpus order, and `rows` equals the chunk
  count. `sqlite_master` must equal the expected corpus schema exactly (the same object names,
  types and normalized SQL), so an imported corpus cannot carry extra triggers, views or tables.
- Semantic: `absent` (lexical-only) | `enabled` | `disabled` (identity differs from the model
  lock entry for the configured embedding model, or from the runtime's reported digest/dimension;
  the message carries reindex guidance; also `disabled` with "run `models pull`" guidance when the
  model lock has no embedding entry) | `unverified` (lock matches but the runtime is unreachable,
  or no runtime was supplied). The validator takes an optional runtime: `index validate`, build
  and activation supply one, while bundle import and inspect never do, so bundles stay socket-free
  (FR-022). The runtime is queried only with `/api/tags` and `/api/show`; there are never
  embedding requests.

## R10. Bundles (FR-018–FR-020, clarification Q3)

**Decision**: format = POSIX tar compressed with gzip (stdlib `tarfile`), extension
`.score-bundle.tar.gz`. First member `bundle-manifest.json`, then `snapshot/<file>` for every
snapshot file. Export streams files and records SHA-256 and size. It refuses when the manifest
lists license-review documents, unless `--acknowledge-license-review "<reason>"` is given; the
reason and file list are then recorded. Import runs in **two passes** over the archive:

1. Scan headers only (streamed decompression, no writes). Reject any member that is not a
   regular file, or whose name is absolute, contains `..`, empty, `.` or backslash segments, is
   outside `bundle-manifest.json` / `snapshot/`, or is a duplicate. Stop at entry 10 001 (count
   cap). Sum the sizes against the 2 GiB cap. Parse `bundle-manifest.json` (≤ 1 MiB) and check its
   format and schema versions. Require the declared total to equal the header sum. Require free
   disk ≥ total + 1 GiB margin.
2. Extract into `data/staging/import-<job>/` with `safe_relative_path` + `ensure_within` (F002),
   `O_CREAT | O_EXCL`, byte-counting against the header size, and hashing while writing. Then
   verify hashes against the bundle manifest and run the full validator. Then register: the same
   snapshot ID, state `validated`. If the ID already exists with the same `manifest_sha256`, it
   is a no-op success; with a different one, refuse.

Python 3.12's `tarfile` `filter="data"` is **not** relied on alone. We never call `extractall`;
our own checks run first (defense in depth, and deterministic error messages).

**Alternatives**: zip was rejected (central directory at the end allows mismatched local
headers; tar headers are simpler to stream-check). zstd compression was rejected (new
dependency; vectors compress poorly anyway).

## R11. Readiness and doctor integration (FR-021)

**Decision**: `CorpusState` gains `COMPATIBLE`. `FileCorpusProbe` opens `catalog.sqlite`
read-only (`mode=ro`): `user_version` newer → `INCOMPATIBLE`; there is an active pointer whose
snapshot row is `active`, its `manifest.json` exists and its schema is supported →
`COMPATIBLE`; no active snapshot → `ABSENT`. Readiness: search stays unavailable with
`not_implemented` (F004), and chat also gets `not_implemented` while a compatible corpus exists
(F005). Otherwise chat would turn "available" merely because the corpus appeared. `doctor`
guidance for `CORPUS_ABSENT` → "run `score-assistant index build --activate`". The probe does not
hash files (it runs on every readiness refresh). Full verification happens at activation and
in `index validate`.

## R12. Retention of sources (FR-015)

**Decision**: after each activation, always keep the active snapshot **and the current rollback
target** (`previous_id` of the latest activation-history row, FR-015 "active and previous").
Then fill up to `retention_count` (default 2, minimum 2) with the newest remaining non-deleted,
non-failed snapshots. Delete older unpinned
ones. Then compute referenced revisions = the union of each retained snapshot manifest's
`source_revisions` and the current `source-lock.json`. Delete
`data/sources/<id>/<rev>/` directories not referenced, and `data/cache/git/<id>.git` for source
IDs that are neither in the current lock nor in any retained snapshot. `validated`, never
activated snapshots count toward retention like retired ones (newest kept). Order per snapshot:
take the exclusive pin lock → remove the directory → mark the row `deleted` → remove the pin
file. After a crash mid-deletion the row is still `retired`, but its files are incomplete.
Activating it fails checksum verification, and the next retention run finishes the deletion
(missing files tolerated).

## R13. Threat boundary for local files

Snapshot files are 0444 and verified at validation, activation and rollback. They are **not**
re-hashed on every reader open (the cost is proportional to snapshot size on each request).
This protects against accidental modification and interrupted writes, not against a malicious
process running as the same OS user, which could equally alter the application itself. That is
consistent with the local single-user threat model (master spec §12.1). Bundles and anything
under `data/staging/import-*` are fully untrusted until validated (R10).

## Resolved unknowns

| Unknown | Resolution |
| --- | --- |
| Embedding context bound, dimension, prefixes | R1 (2048, 768, `search_document: `) |
| Overflow behaviour | R1 (silent by default → `truncate:false`) |
| Token-count method | R2 (`pretoken-v1`, cap 1 800) |
| Vector library | R5 (NumPy, new dependency) |
| Cross-process pin mechanism | R8 (`flock` per snapshot) |
| Bundle format | R10 (tar.gz, two-pass import) |
| Whether exports are chunked | R3 (no; entities/relations only) |
| SC-001 feasibility | ~20 k chunks ÷ 70/s ≈ 5 min embedding + normalize ≈ 25 s; rebuild with reuse needs no embedding calls |
