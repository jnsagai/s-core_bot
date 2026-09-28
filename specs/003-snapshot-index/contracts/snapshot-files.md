# Contract: Snapshot Directory (F003)

`data/snapshots/<snapshot_id>/`. It is immutable after publish: files are mode 0444, and the
directory is only ever deleted whole by retention.

```text
manifest.json              # SnapshotManifest (data-model.md); not listed in its own `files`
corpus.sqlite              # schema below, user_version = 1, journal_mode=DELETE, vacuumed
embeddings.f32             # only when semantic = present
embedding-manifest.json    # only when semantic = present
reports/coverage.json      # F002 CoverageReport for the lock used
reports/build-validation.json  # ValidationReport produced before publish
```

Validation rejects any file present but not listed in `manifest.files`.

## `manifest.json` (schema_version 1)

```json
{
  "schema_version": 1,
  "snapshot_id": "20260928T101500Z-3fa2b1c9",
  "created_at": "2026-09-28T10:15:00Z",
  "app_version": "0.1.0",
  "lock_sha256": "…",
  "source_revisions": {"score-platform": "e2373d8…", "score-platform-needs": "0cb3df7…"},
  "sources": [{"source_id": "score-platform", "kind": "git", "status": "ok", "required": true,
               "revision": "e2373d8…", "revision_status": "pinned"}],
  "processing_hashes": {"score-platform": "…"},
  "chunker_version": "1",
  "chunker_config_sha256": "…",
  "token_count_method": "pretoken-v1",
  "semantic": "present",
  "embedding": {"provider": "ollama", "model_tag": "nomic-embed-text:latest",
                "model_digest": "0a109f42…", "dimension": 768,
                "preprocessing_revision": "…", "normalization": "l2-float32"},
  "embedding_context_tokens": 2048,
  "counts": {"documents": 0, "entities": 0, "relations": 0, "chunks": 0,
             "chunks_by_kind": {"prose": 0, "need": 0, "table": 0, "code": 0,
                                "literal": 0, "diagram": 0},
             "embedded_reused": 0, "embedded_new": 0},
  "coverage": {"sources": [{"source_id": "…", "status": "ok", "selected": 0, "included": 0,
                            "partial": 0, "failed": 0, "entities": 0}],
               "limitations": ["optional source X failed: …",
                               "needs-export sources contribute entities only, no chunks"]},
  "license_review": [{"source_id": "score-process", "path": "…", "spdx": "CC-BY-SA-4.0"}],
  "corpus_schema_version": 1,
  "files": [{"path": "corpus.sqlite", "sha256": "…", "size": 0}]
}
```

(Counts are illustrative placeholders, not measurements.) Readers MUST refuse `schema_version` or
`corpus_schema_version` greater than supported (`SCHEMA_UNSUPPORTED`) before reading other fields.

## `embedding-manifest.json` (schema_version 1)

```json
{"schema_version": 1, "identity": {"…": "as above"}, "dtype": "<f4", "rows": 12345,
 "dimension": 768, "file": "embeddings.f32", "sha256": "…",
 "row_chunk_ids": ["…"], "reused_from": {"20260927T…": 11000}}
```

`embeddings.f32`: raw little-endian float32, C order, `rows × dimension`, size exactly
`rows × dimension × 4` bytes. Row *i* is the vector of `row_chunk_ids[i]`, which equals the
*i*-th chunk in `chunks` ordered by `rowid`.

## `corpus.sqlite` (user_version 1)

```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);   -- snapshot_id, chunker_version, …
CREATE TABLE documents (
  document_key TEXT PRIMARY KEY, source_id TEXT NOT NULL, revision TEXT NOT NULL,
  path TEXT NOT NULL, format TEXT NOT NULL, title TEXT, status TEXT NOT NULL,
  license_spdx TEXT, license_basis TEXT NOT NULL, redistribution TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL, normalized_sha256 TEXT NOT NULL, processing_hash TEXT NOT NULL,
  UNIQUE (source_id, path));
CREATE TABLE entities (
  key TEXT PRIMARY KEY, need_id TEXT NOT NULL, source_id TEXT NOT NULL, type TEXT NOT NULL,
  title TEXT NOT NULL, document_key TEXT NOT NULL REFERENCES documents,
  path TEXT NOT NULL, line_start INTEGER, line_end INTEGER, origin TEXT NOT NULL,
  revision_status TEXT NOT NULL,             -- export entities: 'unverified'
  options_json TEXT NOT NULL, export_fields_json TEXT);
CREATE INDEX entities_need_id ON entities (need_id);
CREATE TABLE relations (                     -- one row per link item
  id INTEGER PRIMARY KEY, from_key TEXT NOT NULL REFERENCES entities, via TEXT NOT NULL,
  target_id TEXT NOT NULL, qualifier TEXT, raw TEXT NOT NULL,
  resolution TEXT NOT NULL CHECK (resolution IN ('resolved','ambiguous','unresolved','malformed')),
  resolved_keys_json TEXT NOT NULL);
CREATE INDEX relations_from ON relations (from_key);
CREATE INDEX relations_target ON relations (target_id);
CREATE TABLE chunks (
  rowid INTEGER PRIMARY KEY,                 -- = embedding row + 1 order; assigned in corpus order
  chunk_id TEXT NOT NULL UNIQUE, document_key TEXT NOT NULL REFERENCES documents,
  ordinal INTEGER NOT NULL, source_id TEXT NOT NULL, revision TEXT NOT NULL, path TEXT NOT NULL,
  origin_path TEXT NOT NULL, heading_path_json TEXT NOT NULL, heading_path TEXT NOT NULL,
  kind TEXT NOT NULL, text TEXT NOT NULL, embedding_input TEXT NOT NULL,
  line_start INTEGER, line_end INTEGER, entity_keys_json TEXT NOT NULL, need_ids TEXT NOT NULL,
  continuation TEXT, table_row_start INTEGER, table_row_end INTEGER,
  token_estimate INTEGER NOT NULL, embedding_token_estimate INTEGER NOT NULL,
  content_hash TEXT NOT NULL, embedding_input_hash TEXT NOT NULL,
  UNIQUE (document_key, ordinal));
CREATE TABLE chunk_entities (chunk_id TEXT NOT NULL, entity_key TEXT NOT NULL,
  PRIMARY KEY (chunk_id, entity_key)) WITHOUT ROWID;
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  text, heading_path, need_ids, content='chunks', content_rowid='rowid',
  tokenize = "unicode61 remove_diacritics 2 tokenchars '_-.'");
```

`heading_path` is the heading path joined with `" > "` (FTS column); `need_ids` is space-separated.
The corpus holds no vectors and no executable content. Queries use parameters only.
