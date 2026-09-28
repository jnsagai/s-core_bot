"""Snapshot validation: integrity checks plus semantic status (FR-016, research R9).

Integrity failures make a snapshot unusable (exit 1). Semantic status says whether its vectors
may be used with the installed embedding model; a mismatch disables semantic use with reindex
guidance instead of being accepted silently. The runtime is only asked for its model identity,
never for embeddings, and bundle import passes no runtime at all (stays socket-free).
"""

from __future__ import annotations

import shutil
import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import (
    Check,
    ChunkerConfig,
    EmbeddingIdentity,
    SemanticStatus,
    SnapshotManifest,
    ValidationReport,
    preprocessing_revision,
)
from score_docs_assistant.models.lock import read_lock
from score_docs_assistant.models.runtime import EmbeddingProvider, normalize_tag
from score_docs_assistant.storage.corpus_db import (
    corpus_counts,
    expected_schema_objects,
    open_corpus_readonly,
    schema_objects,
)
from score_docs_assistant.storage.manifest import (
    CORPUS_NAME,
    MANIFEST_NAME,
    VECTORS_NAME,
    list_files,
    read_embedding_manifest,
    read_snapshot_manifest,
    sha256_file,
)
from score_docs_assistant.storage.sqlite_util import open_hardened
from score_docs_assistant.storage.vectors import open_vectors, vector_problems

Record = Callable[[str, str | None], bool]

REINDEX = 'rebuild with "score-assistant index build" to reindex with the installed model'


class SnapshotValidator:
    def __init__(
        self,
        *,
        data_dir: Path,
        embedding_model: str,
        chunker_config: ChunkerConfig,
        runtime: EmbeddingProvider | None = None,
    ) -> None:
        self._data = data_dir
        self._tag = normalize_tag(embedding_model)
        self._config = chunker_config
        self._runtime = runtime

    def validate(
        self, directory: Path, *, expected_manifest_sha256: str | None = None
    ) -> ValidationReport:
        checks: list[Check] = []

        def record(check_id: str, problem: str | None) -> bool:
            checks.append(
                Check(id=check_id, status="fail" if problem else "pass", detail=problem or "")
            )
            return problem is None

        snapshot_id = directory.name
        try:
            manifest = read_snapshot_manifest(directory)
        except SnapshotError as exc:
            if exc.code == "SCHEMA_UNSUPPORTED":
                raise
            record("manifest", exc.message)
            return self._report(snapshot_id, checks, "absent", "manifest unreadable", [])
        record("manifest", None)
        snapshot_id = manifest.snapshot_id
        if expected_manifest_sha256 is not None:
            actual = sha256_file(directory / MANIFEST_NAME)
            record(
                "manifest.sha256",
                None
                if actual == expected_manifest_sha256
                else f"{MANIFEST_NAME} changed since it was registered",
            )

        files_ok = self._check_files(directory, manifest, record)
        if files_ok:
            self._check_corpus(directory, manifest, record)
            if manifest.semantic == "present":
                self._check_vectors(directory, manifest, record)
        semantic, detail, guidance = self.semantic_status(manifest)
        return self._report(snapshot_id, checks, semantic, detail, guidance)

    @staticmethod
    def _report(
        snapshot_id: str,
        checks: list[Check],
        semantic: SemanticStatus,
        detail: str,
        guidance: list[str],
    ) -> ValidationReport:
        return ValidationReport(
            snapshot_id=snapshot_id,
            checked_at=datetime.now(UTC),
            integrity=checks,
            integrity_ok=all(c.status == "pass" for c in checks),
            semantic=semantic,
            semantic_detail=detail,
            guidance=guidance,
        )

    @staticmethod
    def _check_files(directory: Path, manifest: SnapshotManifest, record: Record) -> bool:
        listed = {f.path: f for f in manifest.files}
        present = set(list_files(directory))
        ok = True
        for path in sorted(present - set(listed)):
            ok = record(f"file:{path}", f"{path}: not listed in the manifest") and ok
        for path, entry in sorted(listed.items()):
            target = directory / path
            if path not in present or not target.is_file():
                ok = record(f"file:{path}", f"{path}: missing") and ok
            elif target.stat().st_size != entry.size or sha256_file(target) != entry.sha256:
                ok = record(f"file:{path}", f"{path}: checksum mismatch") and ok
        if ok:
            record("files", None)
        return ok

    def _check_corpus(self, directory: Path, manifest: SnapshotManifest, record: Record) -> None:
        try:
            conn = open_corpus_readonly(directory / CORPUS_NAME)
        except SnapshotError as exc:
            if exc.code == "SCHEMA_UNSUPPORTED":
                raise
            record("corpus.open", exc.message)
            return
        except sqlite3.DatabaseError as exc:
            record("corpus.open", str(exc))
            return
        try:
            counts = corpus_counts(conn)
        except sqlite3.DatabaseError as exc:
            record("corpus.counts", str(exc))
            conn.close()
            return
        conn.close()
        expected = manifest.counts
        mismatches = [
            f"{name} {counts[name]} ≠ manifest {getattr(expected, name)}"
            for name in ("documents", "entities", "relations", "chunks")
            if counts[name] != getattr(expected, name)
        ]
        record("corpus.counts", "; ".join(mismatches) or None)
        self._check_corpus_copy(directory / CORPUS_NAME, record)

    def _check_corpus_copy(self, corpus: Path, record: Record) -> None:
        """integrity_check, exact schema and FTS-vs-content check need a writable file; run
        them on a private copy so the published corpus is never opened for writing."""
        scratch = self._data / "staging" / f"validate-{uuid.uuid4().hex}"
        scratch.mkdir(parents=True)
        try:
            copy = scratch / CORPUS_NAME
            shutil.copyfile(corpus, copy)
            conn = open_hardened(copy, readonly=False)
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
                record("corpus.integrity", None if result == "ok" else str(result))
                objects = schema_objects(conn)
                expected = expected_schema_objects()
                differing = sorted({o[1] for o in set(objects) ^ set(expected)})
                record(
                    "corpus.schema",
                    f"unexpected or altered schema objects: {differing}" if differing else None,
                )
                try:
                    conn.execute(
                        "INSERT INTO chunks_fts(chunks_fts, rank) VALUES ('integrity-check', 1)"
                    )
                    record("corpus.fts", None)
                except sqlite3.DatabaseError as exc:
                    record("corpus.fts", f"full-text index inconsistent: {exc}")
            finally:
                conn.close()
        except sqlite3.DatabaseError as exc:
            record("corpus.integrity", str(exc))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    @staticmethod
    def _check_vectors(directory: Path, manifest: SnapshotManifest, record: Record) -> None:
        try:
            emb = read_embedding_manifest(directory)
        except SnapshotError as exc:
            if exc.code == "SCHEMA_UNSUPPORTED":
                raise
            record("vectors.manifest", exc.message)
            return
        problems: list[str] = []
        if manifest.embedding != emb.identity:
            problems.append("embedding identity differs between manifests")
        if emb.dimension != emb.identity.dimension:
            problems.append("dimension differs from identity")
        listed = {f.path: f.sha256 for f in manifest.files}
        if listed.get(VECTORS_NAME) != emb.sha256:
            problems.append("vector file hash differs from the embedding manifest")
        if emb.rows != manifest.counts.chunks or len(emb.row_chunk_ids) != emb.rows:
            problems.append(f"rows {emb.rows} ≠ chunks {manifest.counts.chunks}")
        record("vectors.manifest", "; ".join(problems) or None)
        try:
            matrix = open_vectors(directory / VECTORS_NAME, emb.rows, emb.dimension)
        except SnapshotError as exc:
            record("vectors.shape", exc.message)
            return
        record("vectors.shape", None)
        record("vectors.values", "; ".join(vector_problems(matrix)) or None)
        conn = open_corpus_readonly(directory / CORPUS_NAME)
        try:
            ids = [r[0] for r in conn.execute("SELECT chunk_id FROM chunks ORDER BY rowid")]
        finally:
            conn.close()
        record(
            "vectors.row_map",
            None if ids == emb.row_chunk_ids else "row → chunk map differs from corpus order",
        )

    def semantic_status(self, manifest: SnapshotManifest) -> tuple[SemanticStatus, str, list[str]]:
        if manifest.semantic == "absent" or manifest.embedding is None:
            return "absent", "lexical-only snapshot (no vectors)", []
        identity = manifest.embedding
        lock = read_lock(self._data / "model-lock.json")
        entry = lock.entry_for_role("embedding") if lock is not None else None
        if entry is None:
            return (
                "disabled",
                "the model lock has no embedding model entry",
                ["run `score-assistant models pull` to install and lock the embedding model"],
            )
        expected_revision = preprocessing_revision(self._config)
        mismatch = self._mismatch(
            identity,
            tag=normalize_tag(entry.tag),
            digest=entry.digest.removeprefix("sha256:"),
            dimension=None,
            revision=expected_revision,
            where="model lock",
        )
        if mismatch:
            return "disabled", mismatch, [REINDEX]
        if self._runtime is None:
            return "unverified", "matches the model lock; runtime identity not checked", []
        try:
            live = self._runtime.identity()
        except SnapshotError as exc:
            return "unverified", f"matches the model lock; runtime unreachable ({exc.message})", []
        mismatch = self._mismatch(
            identity,
            tag=live.model_tag,
            digest=live.model_digest,
            dimension=live.dimension,
            revision=live.preprocessing_revision,
            where="installed runtime model",
        )
        if mismatch:
            return "disabled", mismatch, [REINDEX]
        return "enabled", "matches the model lock and the installed runtime model", []

    @staticmethod
    def _mismatch(
        identity: EmbeddingIdentity,
        *,
        tag: str,
        digest: str,
        dimension: int | None,
        revision: str,
        where: str,
    ) -> str:
        problems = []
        if identity.model_tag != tag:
            problems.append(f"model {tag} ({where}) ≠ snapshot {identity.model_tag}")
        if identity.model_digest != digest:
            problems.append(
                f"model digest {digest[:12]}… ({where}) differs from snapshot "
                f"{identity.model_digest[:12]}…"
            )
        if dimension is not None and identity.dimension != dimension:
            problems.append(f"dimension {dimension} ({where}) ≠ snapshot {identity.dimension}")
        if identity.preprocessing_revision != revision:
            problems.append("preprocessing revision differs from this release")
        return "; ".join(problems)
