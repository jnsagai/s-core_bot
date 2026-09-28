"""`corpus.sqlite`: documents, entities, relations, chunks and the FTS5 index (FR-006).

Schema: specs/003-snapshot-index/contracts/snapshot-files.md. Written once in staging with
`journal_mode=DELETE` (no sidecar files to checksum), vacuumed and closed before hashing. Readers
open it read-only and immutable through `open_hardened`.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.ingestion import Entity, NormalizedDocument
from score_docs_assistant.domain.snapshots import CORPUS_SCHEMA_VERSION, Chunk
from score_docs_assistant.storage.sqlite_util import open_hardened

SCHEMA: tuple[str, ...] = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE documents (
  document_key TEXT PRIMARY KEY, source_id TEXT NOT NULL, revision TEXT NOT NULL,
  path TEXT NOT NULL, format TEXT NOT NULL, title TEXT, status TEXT NOT NULL,
  license_spdx TEXT, license_basis TEXT NOT NULL, redistribution TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL, normalized_sha256 TEXT NOT NULL, processing_hash TEXT NOT NULL,
  UNIQUE (source_id, path))""",
    """CREATE TABLE entities (
  key TEXT PRIMARY KEY, need_id TEXT NOT NULL, source_id TEXT NOT NULL, type TEXT NOT NULL,
  title TEXT NOT NULL, document_key TEXT NOT NULL REFERENCES documents,
  path TEXT NOT NULL, line_start INTEGER, line_end INTEGER, origin TEXT NOT NULL,
  revision_status TEXT NOT NULL, options_json TEXT NOT NULL, export_fields_json TEXT)""",
    "CREATE INDEX entities_need_id ON entities (need_id)",
    """CREATE TABLE relations (
  id INTEGER PRIMARY KEY, from_key TEXT NOT NULL REFERENCES entities, via TEXT NOT NULL,
  target_id TEXT NOT NULL, qualifier TEXT, raw TEXT NOT NULL,
  resolution TEXT NOT NULL CHECK (resolution IN ('resolved','ambiguous','unresolved','malformed')),
  resolved_keys_json TEXT NOT NULL)""",
    "CREATE INDEX relations_from ON relations (from_key)",
    "CREATE INDEX relations_target ON relations (target_id)",
    """CREATE TABLE chunks (
  rowid INTEGER PRIMARY KEY,
  chunk_id TEXT NOT NULL UNIQUE, document_key TEXT NOT NULL REFERENCES documents,
  ordinal INTEGER NOT NULL, source_id TEXT NOT NULL, revision TEXT NOT NULL, path TEXT NOT NULL,
  origin_path TEXT NOT NULL, heading_path_json TEXT NOT NULL, heading_path TEXT NOT NULL,
  kind TEXT NOT NULL, text TEXT NOT NULL, embedding_input TEXT NOT NULL,
  line_start INTEGER, line_end INTEGER, entity_keys_json TEXT NOT NULL, need_ids TEXT NOT NULL,
  continuation TEXT, table_row_start INTEGER, table_row_end INTEGER,
  token_estimate INTEGER NOT NULL, embedding_token_estimate INTEGER NOT NULL,
  content_hash TEXT NOT NULL, embedding_input_hash TEXT NOT NULL,
  UNIQUE (document_key, ordinal))""",
    """CREATE TABLE chunk_entities (chunk_id TEXT NOT NULL, entity_key TEXT NOT NULL,
  PRIMARY KEY (chunk_id, entity_key)) WITHOUT ROWID""",
    """CREATE VIRTUAL TABLE chunks_fts USING fts5(
  text, heading_path, need_ids, content='chunks', content_rowid='rowid',
  tokenize = "unicode61 remove_diacritics 2 tokenchars '_-.'")""",
)

CHUNK_COLUMNS = (
    "chunk_id",
    "document_key",
    "ordinal",
    "source_id",
    "revision",
    "path",
    "origin_path",
    "heading_path_json",
    "heading_path",
    "kind",
    "text",
    "embedding_input",
    "line_start",
    "line_end",
    "entity_keys_json",
    "need_ids",
    "continuation",
    "table_row_start",
    "table_row_end",
    "token_estimate",
    "embedding_token_estimate",
    "content_hash",
    "embedding_input_hash",
)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def write_corpus(
    path: Path,
    *,
    snapshot_id: str,
    documents: Sequence[NormalizedDocument],
    entities: Sequence[Entity],
    chunks: Sequence[Chunk],
    meta: dict[str, str] | None = None,
) -> dict[str, int]:
    """Write a new corpus file; returns row counts. `chunks` must already be in corpus order."""
    if path.exists():
        raise FileExistsError(path)
    conn = open_hardened(path, readonly=False)
    try:
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute(f"PRAGMA user_version = {CORPUS_SCHEMA_VERSION}")
        with conn:
            for statement in SCHEMA:
                conn.execute(statement)
            conn.executemany(
                "INSERT INTO meta VALUES (?, ?)",
                sorted({"snapshot_id": snapshot_id, **(meta or {})}.items()),
            )
            conn.executemany(
                "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        d.document_key,
                        d.source_id,
                        d.revision,
                        d.path,
                        d.format,
                        d.title,
                        d.status,
                        d.license.spdx,
                        d.license.basis,
                        d.license.redistribution,
                        d.raw_sha256,
                        d.normalized_sha256,
                        d.processing_hash,
                    )
                    for d in sorted(documents, key=lambda d: (d.source_id, d.path))
                ],
            )
            conn.executemany(
                "INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        e.key,
                        e.need_id,
                        e.source_id,
                        e.type,
                        e.title,
                        e.document_key,
                        e.path,
                        e.line_start,
                        e.line_end,
                        e.origin,
                        e.revision_status,
                        _json(e.options),
                        None if e.export_fields is None else _json(e.export_fields),
                    )
                    for e in sorted(entities, key=lambda e: e.key)
                ],
            )
            conn.executemany(
                "INSERT INTO relations (from_key, via, target_id, qualifier, raw, resolution,"
                " resolved_keys_json) VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        e.key,
                        link.via,
                        link.target_id,
                        link.qualifier,
                        link.raw,
                        link.resolution,
                        _json(link.resolved_keys),
                    )
                    for e in sorted(entities, key=lambda e: e.key)
                    for link in e.links
                ],
            )
            placeholders = ",".join("?" * len(CHUNK_COLUMNS))
            conn.executemany(
                f"INSERT INTO chunks ({','.join(CHUNK_COLUMNS)}) VALUES ({placeholders})",
                [
                    (
                        c.chunk_id,
                        c.document_key,
                        c.ordinal,
                        c.source_id,
                        c.revision,
                        c.path,
                        c.origin_path,
                        _json(c.heading_path),
                        " > ".join(c.heading_path),
                        c.kind,
                        c.text,
                        c.embedding_input,
                        c.line_start,
                        c.line_end,
                        _json(c.entity_keys),
                        " ".join(c.need_ids),
                        c.continuation,
                        c.table_rows[0] if c.table_rows else None,
                        c.table_rows[1] if c.table_rows else None,
                        c.token_estimate,
                        c.embedding_token_estimate,
                        c.content_hash,
                        c.embedding_input_hash,
                    )
                    for c in chunks
                ],
            )
            conn.executemany(
                "INSERT INTO chunk_entities VALUES (?, ?)",
                [(c.chunk_id, key) for c in chunks for key in c.entity_keys],
            )
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
        conn.execute("VACUUM")
        counts = corpus_counts(conn)
    finally:
        conn.close()
    return counts


def corpus_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        for table in ("documents", "entities", "relations", "chunks")
    }


def open_corpus_readonly(path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a published corpus; refuses a newer schema before anything else is read (FR-017)."""
    conn = open_hardened(path, readonly=True, immutable=True, check_same_thread=check_same_thread)
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > CORPUS_SCHEMA_VERSION:
        conn.close()
        raise SnapshotError(
            "SCHEMA_UNSUPPORTED",
            f"{path}: corpus schema {version} is newer than supported {CORPUS_SCHEMA_VERSION}",
        )
    return conn


def expected_schema_objects() -> list[tuple[str, str, str | None]]:
    """(type, name, normalized sql) of every schema object a fresh corpus contains."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        conn = open_hardened(Path(tmp) / "ref.sqlite", readonly=False)
        try:
            for statement in SCHEMA:
                conn.execute(statement)
            return schema_objects(conn)
        finally:
            conn.close()


def schema_objects(conn: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    rows = conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
    return [(t, n, " ".join(s.split()) if s else None) for t, n, s in rows]
