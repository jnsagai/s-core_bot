# Data Model: F003 Immutable Snapshots and Local Embedding Index

Frozen Pydantic models in `src/score_docs_assistant/domain/snapshots.py` unless noted. The
records are independent of SQLite, NumPy and Ollama types (constitution VI). Timestamps are UTC
ISO 8601. Hashes are lowercase hex SHA-256. Canonical hashing reuses
`ingestion/canonical.py` (no floats in hashed records; vectors are never hashed as JSON, only
as file bytes).

## Chunk (`domain/snapshots.py`, produced by `ingestion/chunking.py`)

| Field | Type | Notes |
| --- | --- | --- |
| `chunk_id` | str | `canonical_hash({chunker_version, document_key, ordinal, content_hash})` (R3.11) |
| `document_key` | str | F002 document key |
| `ordinal` | int | 0-based position within the document |
| `source_id`, `revision`, `path` | str | from the document |
| `origin_path` | str | differs from `path` for included lines |
| `heading_path` | list[str] | |
| `kind` | `prose` \| `need` \| `table` \| `code` \| `literal` \| `diagram` | |
| `text` | str | display text: verbatim normalized text, no synthetic prefix |
| `embedding_input` | str | `search_document: ` + prefix + display text (R3.10) |
| `line_start`, `line_end` | int \| None | 1-based inclusive |
| `entity_keys` | list[str] | sorted; non-empty only on `need` chunks (a need is never merged with prose, so keys are unambiguous) |
| `need_ids` | list[str] | the `need_id` part of `entity_keys` (FTS column) |
| `continuation` | str \| None | `"i/n"` (1-based) for split needs/code/tables/paragraphs |
| `table_rows` | tuple[int, int] \| None | body row range for split tables |
| `token_estimate` | int | `pretoken-v1` of `text` |
| `embedding_token_estimate` | int | `pretoken-v1` of `embedding_input`; ≤ `embedding_max_input_tokens` |
| `content_hash` | str | sha256(`text`) |
| `embedding_input_hash` | str | sha256(`embedding_input`) |

Invariants: `(document_key, ordinal)` is unique. Every character of every contributing block's
text appears in at least one chunk of that document (no loss; tested by concatenation minus
overlaps and repeated table headers). Chunk order in the corpus = (source_id, path, ordinal).

## ChunkerConfig (`ingestion/chunking.py`)

`chunker_version: "1"`, `min_tokens: 350`, `max_tokens: 700`, `overlap_tokens: 75`
(50 ≤ x ≤ 100), `embedding_max_input_tokens: 1800`, `prefix_max_tokens: 160`,
`token_count_method: "pretoken-v1"`, `document_prefix: "search_document: "`.
`chunker_config_sha256` = canonical hash of all fields. Values come from `AppConfig.index`
(below); only the version and method are fixed in code.

## EmbeddingIdentity

| Field | Example |
| --- | --- |
| `provider` | `ollama` |
| `model_tag` | `nomic-embed-text:latest` (normalized) |
| `model_digest` | `0a109f42…e59f` |
| `dimension` | 768 |
| `preprocessing_revision` | canonical hash of `{document_prefix, prefix_template_version: 1, truncate: false}` |
| `normalization` | `l2-float32` |

Equality over all six fields gates reuse (FR-008) and semantic validity (FR-016).

## SnapshotManifest (`manifest.json`; schema in [contracts/snapshot-files.md](contracts/snapshot-files.md))

`schema_version: 1`, `snapshot_id`, `created_at`, `app_version`, `lock_sha256`,
`source_revisions: {source_id → revision}`, `sources: [{source_id, kind, status, required,
revision, revision_status}]`, `processing_hashes: {source_id → hash}`, `chunker_version`,
`chunker_config_sha256`, `token_count_method`, `semantic: "present" | "absent"`,
`embedding: EmbeddingIdentity | null`, `embedding_context_tokens: int | null`,
`counts: {documents, entities, relations, chunks, chunks_by_kind, embedded_reused,
embedded_new}`, `coverage: {per-source summary + limitations[]}`,
`license_review: [{source_id, path, spdx}]`, `corpus_schema_version: 1`,
`files: [{path, sha256, size}]` (every file except `manifest.json`, sorted by path).

## EmbeddingManifest (`embedding-manifest.json`)

`schema_version: 1`, `identity: EmbeddingIdentity`, `dtype: "<f4"`, `rows`, `dimension`,
`file: "embeddings.f32"`, `sha256`, `row_chunk_ids: list[str]`, `reused_from:
{snapshot_id → count}` (informational). Absent for lexical-only snapshots.

## CorpusSnapshot (catalog row; [contracts/catalog.md](contracts/catalog.md))

`snapshot_id`, `state`, `created_at`, `validated_at`, `activated_at`, `retired_at`,
`deleted_at`, `manifest_sha256`, `schema_version`, `semantic`, `job_id`, `failure`.

State machine:

```text
building ──validate ok──▶ validated ──activate──▶ active ──(other activated / rollback)──▶ retired
   │                          ▲                                                           │
   └──fail/interrupt──▶ failed │                                  activate/rollback ◀─────┘
                               └── import (verified) ──────────────
retired|validated ──retention (unpinned, beyond count)──▶ deleted (row kept, deleted_at set)
```

Rules: only `validated` or `retired` can become `active`. `failed`/`building`/`deleted` never
can. Exactly one `active` row at most. `failed` rows keep their `failure` reason.

## ActivationRecord (table `activation_history`)

`seq` (autoincrement), `snapshot_id`, `previous_id | null`, `kind: activate|rollback`,
`at`. Rollback target = `previous_id` of the row with the highest `seq`.

## BuildJob

`job_id` (UUID4 hex), `kind: build|import`, `state: running|succeeded|failed`, `pid`,
`started_at`, `finished_at`, `snapshot_id`, `stage` (last entered: `normalizing`, `chunking`,
`writing`, `embedding`, `validating`, `publishing`), `failure`.

## Pin (`storage/pins.py`)

Runtime object, not persisted: `snapshot_id` and an open file descriptor holding
`flock(LOCK_SH)` on `data/pins/<snapshot_id>.pin`. Released on `close()` or process exit.

## ValidationReport (`storage/validation.py`)

`snapshot_id`, `checked_at`, `integrity: list[Check{id, status: pass|fail, detail}]`,
`integrity_ok: bool`, `semantic: enabled|absent|disabled|unverified`, `semantic_detail`,
`guidance: list[str]`. Exit code mapping: integrity fail → 1, else 0.

## BundleManifest (`bundle-manifest.json`; [contracts/bundle.md](contracts/bundle.md))

`bundle_format: 1`, `schema_version` (= snapshot schema), `corpus_schema_version`,
`snapshot_id`, `manifest_sha256`, `created_at`, `app_version`, `files: [{path, sha256,
size}]`, `total_size`, `entry_count`, `license_acknowledgement: {reason, files[]} | null`.

## Configuration additions (`config/schema.py`, `AppConfig.index` / `AppConfig.bundles`)

```yaml
index:
  chunk_min_tokens: 350          # 100 ≤ x ≤ chunk_max_tokens
  chunk_max_tokens: 700          # ≤ embedding_max_input_tokens - 200
  chunk_overlap_tokens: 75       # 50..100
  embedding_max_input_tokens: 1800
  embedding_batch_size: 32       # 1..256
  embedding_timeout_seconds: 120 # per request, 1..600
  retention_count: 2             # ≥ 2
bundles:
  max_total_bytes: 2147483648
  max_entries: 10000
  disk_margin_bytes: 1073741824
```

Unknown keys are rejected, as for every section. Defaults are applied when the sections are
absent, so existing `config/local.yaml` stays valid.

## Error types (`domain/errors.py`)

`SnapshotError(code, message)` base with codes: `BUILD_BUSY`, `REQUIRED_SOURCE_FAILED`,
`CHUNK_UNSPLITTABLE`, `EMBEDDING_UNAVAILABLE`, `EMBEDDING_INPUT_TOO_LONG`,
`EMBEDDING_INVALID_VECTOR`, `SCHEMA_UNSUPPORTED`, `CHECKSUM_MISMATCH`, `NOT_ACTIVATABLE`,
`NO_ROLLBACK_TARGET`, `SNAPSHOT_NOT_FOUND`, `LICENSE_REVIEW_REQUIRED`, `BUNDLE_REJECTED`,
`DISK_INSUFFICIENT`. The CLI maps them to exit 1. `ConfigError` stays exit 2.
