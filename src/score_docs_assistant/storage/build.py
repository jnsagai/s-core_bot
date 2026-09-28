"""`index build`: source lock → validated snapshot (FR-009–FR-012, research R6, R7).

Everything is written under `data/staging/build-<job>/` and moved into `data/snapshots/<id>/`
only after validation. The active snapshot and pointer are never touched here; activation is a
separate, opt-in step. A failed or interrupted build is recovered by the next build, which holds
the single-writer lock. Logs and progress carry IDs and counts only, never document text.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from score_docs_assistant import __version__
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.ingestion import CoverageReport, NormalizedDocument, SourceLock
from score_docs_assistant.domain.snapshots import (
    CORPUS_SCHEMA_VERSION,
    EMBEDDING_MANIFEST_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    BuildStage,
    Chunk,
    ChunkerConfig,
    CoverageSummary,
    EmbeddingIdentity,
    EmbeddingManifest,
    LicenseReviewEntry,
    ManifestCounts,
    ManifestSource,
    SnapshotManifest,
    SourceCoverageSummary,
)
from score_docs_assistant.ingestion.chunking import Chunker
from score_docs_assistant.ingestion.normalize import NormalizationService
from score_docs_assistant.ingestion.tokens import TOKEN_COUNT_METHOD
from score_docs_assistant.models.lock import read_lock as read_model_lock
from score_docs_assistant.models.runtime import EmbeddingProvider, normalize_tag
from score_docs_assistant.sources.lock import read_lock, source_root, verify_files
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.corpus_db import open_corpus_readonly, write_corpus
from score_docs_assistant.storage.locks import IngestLock
from score_docs_assistant.storage.manifest import (
    CORPUS_NAME,
    EMBEDDING_MANIFEST_NAME,
    MANIFEST_NAME,
    VECTORS_NAME,
    dump_json,
    hash_files,
    read_embedding_manifest,
    read_snapshot_manifest,
    sha256_file,
    write_json_file,
)
from score_docs_assistant.storage.pins import Pin
from score_docs_assistant.storage.validation import SnapshotValidator
from score_docs_assistant.storage.vectors import (
    Matrix,
    normalize_rows,
    open_vectors,
    vector_problems,
    write_vectors,
)

StageHook = Callable[[BuildStage], None]
Progress = Callable[[str], None]
EXPORTS_NOTE = "needs-export sources contribute entities and relations only, no chunks"


def chunker_config(config: AppConfig) -> ChunkerConfig:
    index = config.index
    return ChunkerConfig(
        min_tokens=index.chunk_min_tokens,
        max_tokens=index.chunk_max_tokens,
        overlap_tokens=index.chunk_overlap_tokens,
        embedding_max_input_tokens=index.embedding_max_input_tokens,
    )


def new_snapshot_id(job_id: str) -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + job_id[:8]


def directory_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def remove_tree(path: Path) -> None:
    """rmtree that also removes read-only published files (their directories stay writable)."""
    if path.exists():
        shutil.rmtree(path)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@dataclass
class BuildResult:
    snapshot_id: str
    state: str
    semantic: str
    counts: ManifestCounts
    duration_seconds: float
    activated: bool = False
    warnings: list[str] = field(default_factory=list)


class BuildService:
    def __init__(
        self,
        *,
        config: AppConfig,
        profiles_dir: Path,
        provider: EmbeddingProvider | None,
        lexical_only: bool = False,
        stage_hook: StageHook | None = None,
        progress: Progress | None = None,
        free_bytes: Callable[[Path], int] | None = None,
    ) -> None:
        self._config = config
        self._data = config.data_dir
        self._profiles = profiles_dir
        self._provider = provider
        self._lexical_only = lexical_only
        self._stage_hook = stage_hook
        self._progress = progress or (lambda _message: None)
        self._free_bytes = free_bytes or (lambda path: shutil.disk_usage(path).free)
        self._chunker_config = chunker_config(config)

    # --- entry point -------------------------------------------------------------------------

    def run(
        self, lock_path: Path, *, after_publish: Callable[[Catalog, str], list[str]] | None = None
    ) -> BuildResult:
        started = time.monotonic()
        with IngestLock(self._data):
            catalog = Catalog.open(self._data, create=True)
            assert catalog is not None
            with catalog:
                self._recover(catalog)
                self._check_disk(catalog)
                job_id = uuid.uuid4().hex
                snapshot_id = new_snapshot_id(job_id)
                staging = self._data / "staging" / f"build-{job_id}"
                catalog.start_job(job_id, "build", snapshot_id, os.getpid())
                try:
                    result = self._build(catalog, job_id, snapshot_id, staging, lock_path)
                except BaseException as exc:
                    reason = exc.message if isinstance(exc, SnapshotError) else repr(exc)
                    remove_tree(staging)
                    catalog.fail(job_id=job_id, snapshot_id=snapshot_id, reason=reason)
                    raise
                result.duration_seconds = time.monotonic() - started
                if after_publish is not None:
                    result.warnings.extend(after_publish(catalog, snapshot_id))
                    result.activated = True
                    result.state = "active"
                return result

    # --- preflight ---------------------------------------------------------------------------

    def _recover(self, catalog: Catalog) -> None:
        recovered = catalog.recover_interrupted()
        for snapshot_id in recovered:
            self._progress(f"recovered interrupted build {snapshot_id} (marked failed)")
        staging = self._data / "staging"
        if staging.exists():
            for child in staging.iterdir():
                if child.name.startswith(("build-", "import-", "validate-")):
                    remove_tree(child)
        snapshots_dir = self._data / "snapshots"
        for snapshot in catalog.snapshots():
            if snapshot.state == "failed":
                remove_tree(snapshots_dir / snapshot.snapshot_id)

    def _check_disk(self, catalog: Catalog) -> None:
        newest = next(
            (
                s
                for s in catalog.snapshots()
                if s.state in ("active", "validated", "retired")
                and (self._data / "snapshots" / s.snapshot_id).is_dir()
            ),
            None,
        )
        previous = directory_size(self._data / "snapshots" / newest.snapshot_id) if newest else 0
        required = self._config.diagnostics.disk_margin_bytes + previous
        free = self._free_bytes(self._data)
        if free < required:
            raise SnapshotError(
                "DISK_INSUFFICIENT",
                f"need {required} bytes free under {self._data} (margin + newest snapshot), "
                f"only {free} available",
            )

    def _stage(self, catalog: Catalog, job_id: str, stage: BuildStage) -> None:
        catalog.set_stage(job_id, stage)
        self._progress(f"stage {stage}")
        if self._stage_hook is not None:
            self._stage_hook(stage)

    def _check_lock(self, lock: SourceLock) -> None:
        for source in lock.sources:
            if not source.required:
                continue
            if source.status != "ok" or source.revision is None:
                raise SnapshotError(
                    "REQUIRED_SOURCE_FAILED",
                    f"required source {source.source_id} is {source.status} in the lock",
                )
            problems = verify_files(
                source_root(self._data, source.source_id, source.revision), source
            )
            if problems:
                raise SnapshotError(
                    "REQUIRED_SOURCE_FAILED",
                    f"required source {source.source_id}: {len(problems)} file(s) missing or "
                    f"changed on disk (first: {problems[0]}); run `sources sync`",
                )

    def _embedding_preflight(self) -> tuple[EmbeddingIdentity, int] | None:
        if self._lexical_only:
            return None
        hint = " (use --lexical-only for a keyword-only snapshot)"
        if self._provider is None:
            raise SnapshotError("EMBEDDING_UNAVAILABLE", "no embedding runtime configured" + hint)
        try:
            identity = self._provider.identity()
            context = self._provider.context_tokens()
        except SnapshotError as exc:
            raise SnapshotError("EMBEDDING_UNAVAILABLE", exc.message + hint) from exc
        lock = read_model_lock(self._data / "model-lock.json")
        entry = lock.entry_for_role("embedding") if lock is not None else None
        if entry is None:
            raise SnapshotError(
                "EMBEDDING_UNAVAILABLE",
                "the model lock has no embedding model; run `score-assistant models pull`" + hint,
            )
        if (
            normalize_tag(entry.tag) != identity.model_tag
            or entry.digest.removeprefix("sha256:") != identity.model_digest
        ):
            raise SnapshotError(
                "EMBEDDING_UNAVAILABLE",
                f"installed {identity.model_tag} ({identity.model_digest[:12]}…) differs from the "
                f"model lock ({entry.digest[:12]}…); run `models pull` to requalify" + hint,
            )
        if self._chunker_config.embedding_max_input_tokens >= context:
            raise SnapshotError(
                "EMBEDDING_UNAVAILABLE",
                f"embedding input cap {self._chunker_config.embedding_max_input_tokens} is not "
                f"below the model context bound {context}",
            )
        return identity, context

    # --- pipeline ----------------------------------------------------------------------------

    def _build(
        self, catalog: Catalog, job_id: str, snapshot_id: str, staging: Path, lock_path: Path
    ) -> BuildResult:
        lock = read_lock(lock_path)
        lock_sha = hashlib.sha256(lock_path.read_bytes()).hexdigest()
        self._check_lock(lock)
        embedding = self._embedding_preflight()

        self._stage(catalog, job_id, "normalizing")
        outcome = NormalizationService(lock, lock_sha, self._data, self._profiles).run()
        if outcome.exit_code != 0:
            failed = [s.source_id for s in outcome.report.sources if s.status == "failed"]
            raise SnapshotError("REQUIRED_SOURCE_FAILED", f"normalization failed for {failed}")

        self._stage(catalog, job_id, "chunking")
        chunks = Chunker(self._chunker_config).chunk_all(outcome.documents, outcome.entities)
        self._progress(
            f"chunks {len(chunks)} ("
            + ", ".join(f"{k} {v}" for k, v in sorted(_kinds(chunks).items()))
            + ")"
        )

        self._stage(catalog, job_id, "writing")
        staging.mkdir(parents=True)
        counts = write_corpus(
            staging / CORPUS_NAME,
            snapshot_id=snapshot_id,
            documents=outcome.documents,
            entities=outcome.entities,
            chunks=chunks,
            meta={"chunker_version": self._chunker_config.chunker_version},
        )
        write_json_file(staging / "reports" / "coverage.json", outcome.report)

        self._stage(catalog, job_id, "embedding")
        reused = new = 0
        if embedding is not None:
            identity, _context = embedding
            reused, new = self._embed(catalog, staging, chunks, identity)

        self._stage(catalog, job_id, "validating")
        manifest = self._manifest(
            snapshot_id=snapshot_id,
            lock=lock,
            lock_sha=lock_sha,
            documents=outcome.documents,
            report=outcome.report,
            counts=ManifestCounts(
                documents=counts["documents"],
                entities=counts["entities"],
                relations=counts["relations"],
                chunks=counts["chunks"],
                chunks_by_kind=_kinds(chunks),
                embedded_reused=reused,
                embedded_new=new,
            ),
            embedding=embedding,
            staging=staging,
        )
        self._validate(staging, manifest)

        self._stage(catalog, job_id, "publishing")
        target = self._publish(staging, snapshot_id)
        catalog.publish(
            snapshot_id=snapshot_id,
            job_id=job_id,
            manifest_sha256=sha256_file(target / MANIFEST_NAME),
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            semantic=manifest.semantic,
            chunks=manifest.counts.chunks,
        )
        self._progress(f"published {snapshot_id} (validated)")
        return BuildResult(
            snapshot_id=snapshot_id,
            state="validated",
            semantic=manifest.semantic,
            counts=manifest.counts,
            duration_seconds=0.0,
        )

    def _reuse_index(
        self, catalog: Catalog, identity: EmbeddingIdentity, needed: set[str]
    ) -> tuple[dict[str, np.ndarray], dict[str, int]]:
        """Vectors for `needed` embedding-input hashes from retained snapshots with an identical
        identity (FR-008). Each source snapshot is pinned while it is read."""
        found: dict[str, np.ndarray] = {}
        per_snapshot: dict[str, int] = {}
        for snapshot in catalog.snapshots():
            if not needed - found.keys():
                break
            if snapshot.state not in ("validated", "active", "retired"):
                continue
            if snapshot.semantic != "present":
                continue
            directory = self._data / "snapshots" / snapshot.snapshot_id
            try:
                with Pin(self._data, snapshot.snapshot_id):
                    if not directory.is_dir():
                        continue
                    emb = read_embedding_manifest(directory)
                    if emb.identity != identity:
                        continue
                    matrix = open_vectors(directory / VECTORS_NAME, emb.rows, emb.dimension)
                    conn = open_corpus_readonly(directory / CORPUS_NAME)
                    try:
                        rows = conn.execute(
                            "SELECT rowid, embedding_input_hash FROM chunks ORDER BY rowid"
                        ).fetchall()
                    finally:
                        conn.close()
                    for rowid, input_hash in rows:
                        if input_hash in needed and input_hash not in found:
                            vector = np.array(matrix[rowid - 1], dtype=np.float32)
                            if not vector_problems(vector.reshape(1, -1)):
                                found[input_hash] = vector
                                per_snapshot[snapshot.snapshot_id] = (
                                    per_snapshot.get(snapshot.snapshot_id, 0) + 1
                                )
            except (SnapshotError, OSError, sqlite3.DatabaseError) as exc:
                self._progress(f"skipping reuse from {snapshot.snapshot_id}: {exc}")
        return found, per_snapshot

    def _embed(
        self,
        catalog: Catalog,
        staging: Path,
        chunks: Sequence[Chunk],
        identity: EmbeddingIdentity,
    ) -> tuple[int, int]:
        assert self._provider is not None
        needed = {c.embedding_input_hash for c in chunks}
        reuse, per_snapshot = self._reuse_index(catalog, identity, needed)
        missing: dict[str, str] = {}
        for chunk in chunks:
            if chunk.embedding_input_hash not in reuse:
                missing.setdefault(chunk.embedding_input_hash, chunk.embedding_input)
        fresh: dict[str, np.ndarray] = {}
        items = list(missing.items())
        batch = self._config.index.embedding_batch_size
        for start in range(0, len(items), batch):
            part = items[start : start + batch]
            try:
                vectors = self._provider.embed([text for _, text in part])
            except SnapshotError as exc:
                if exc.code == "EMBEDDING_INPUT_TOO_LONG":
                    names = [
                        f"{c.source_id}:{c.path}#{c.ordinal}"
                        for c in chunks
                        if c.embedding_input_hash in {h for h, _ in part}
                    ]
                    raise SnapshotError(
                        "EMBEDDING_INPUT_TOO_LONG",
                        f"{exc.message} (batch containing {', '.join(names[:5])})",
                    ) from exc
                raise
            matrix = normalize_rows(vectors, identity.dimension)
            for (input_hash, _), vector in zip(part, matrix, strict=True):
                fresh[input_hash] = vector
            self._progress(f"embedding {min(start + batch, len(items))}/{len(items)}")
        rows: Matrix = np.zeros((len(chunks), identity.dimension), dtype=np.float32)
        for index, chunk in enumerate(chunks):
            source = reuse.get(chunk.embedding_input_hash)
            rows[index] = source if source is not None else fresh[chunk.embedding_input_hash]
        write_vectors(staging / VECTORS_NAME, rows)
        write_json_file(
            staging / EMBEDDING_MANIFEST_NAME,
            EmbeddingManifest(
                schema_version=EMBEDDING_MANIFEST_SCHEMA_VERSION,
                identity=identity,
                rows=len(chunks),
                dimension=identity.dimension,
                sha256=sha256_file(staging / VECTORS_NAME),
                row_chunk_ids=[c.chunk_id for c in chunks],
                reused_from=per_snapshot,
            ),
        )
        reused_count = sum(1 for c in chunks if c.embedding_input_hash in reuse)
        self._progress(
            f"embedded {len(chunks)} rows (reused {reused_count}; "
            f"{len(fresh)} unique inputs sent to the runtime)"
        )
        return reused_count, len(chunks) - reused_count

    def _manifest(
        self,
        *,
        snapshot_id: str,
        lock: SourceLock,
        lock_sha: str,
        documents: Sequence[NormalizedDocument],
        report: CoverageReport,
        counts: ManifestCounts,
        embedding: tuple[EmbeddingIdentity, int] | None,
        staging: Path,
    ) -> SnapshotManifest:
        processing: dict[str, str] = {}
        for doc in documents:
            processing.setdefault(doc.source_id, doc.processing_hash)
        limitations = [
            f"optional source {s.source_id} failed: {s.failure or 'unknown'}"
            for s in lock.sources
            if not s.required and s.status != "ok"
        ]
        if any(s.kind == "needs-export" for s in lock.sources):
            limitations.append(EXPORTS_NOTE)
        return SnapshotManifest(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            snapshot_id=snapshot_id,
            created_at=datetime.now(UTC),
            app_version=__version__,
            lock_sha256=lock_sha,
            source_revisions={
                s.source_id: s.revision for s in lock.sources if s.revision and s.status == "ok"
            },
            sources=[
                ManifestSource(
                    source_id=s.source_id,
                    kind=s.kind,
                    status=s.status,
                    required=s.required,
                    revision=s.revision,
                    revision_status=s.revision_status,
                )
                for s in lock.sources
            ],
            processing_hashes=processing,
            chunker_version=self._chunker_config.chunker_version,
            chunker_config_sha256=self._chunker_config.sha256(),
            token_count_method=TOKEN_COUNT_METHOD,
            semantic="absent" if embedding is None else "present",
            embedding=None if embedding is None else embedding[0],
            embedding_context_tokens=None if embedding is None else embedding[1],
            counts=counts,
            coverage=CoverageSummary(
                sources=[
                    SourceCoverageSummary(
                        source_id=c.source_id,
                        status=c.status,
                        selected=c.selected,
                        included=c.included,
                        partial=c.partial,
                        failed=len(c.failed),
                        entities=c.entities,
                    )
                    for c in report.sources
                ],
                limitations=limitations,
            ),
            license_review=[
                LicenseReviewEntry(source_id=d.source_id, path=d.path, spdx=d.license.spdx)
                for d in sorted(documents, key=lambda d: (d.source_id, d.path))
                if d.license.redistribution == "requires_review"
            ],
            corpus_schema_version=CORPUS_SCHEMA_VERSION,
            files=hash_files(staging),
        )

    def _validate(self, staging: Path, manifest: SnapshotManifest) -> None:
        """Validate content, then record the report in the snapshot and re-list the manifest so
        the report itself is covered by checksums."""
        (staging / MANIFEST_NAME).write_bytes(dump_json(manifest))
        validator = SnapshotValidator(
            data_dir=self._data,
            embedding_model=self._config.runtime.embedding_model,
            chunker_config=self._chunker_config,
            runtime=self._provider if manifest.semantic == "present" else None,
        )
        report = validator.validate(staging)
        if not report.integrity_ok:
            failed = [f"{c.id}: {c.detail}" for c in report.integrity if c.status == "fail"]
            raise SnapshotError("BUILD_FAILED", "validation failed: " + "; ".join(failed))
        (staging / MANIFEST_NAME).unlink()
        write_json_file(staging / "reports" / "build-validation.json", report)
        final = manifest.model_copy(update={"files": hash_files(staging)})
        write_json_file(staging / MANIFEST_NAME, final)
        if read_snapshot_manifest(staging) != final:
            raise SnapshotError("BUILD_FAILED", "manifest round-trip mismatch")

    def _publish(self, staging: Path, snapshot_id: str) -> Path:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                with path.open("rb") as handle:
                    os.fsync(handle.fileno())
                path.chmod(0o444)
        for directory in sorted({p.parent for p in staging.rglob("*")} | {staging}):
            _fsync_dir(directory)
        snapshots = self._data / "snapshots"
        snapshots.mkdir(parents=True, exist_ok=True)
        target = snapshots / snapshot_id
        os.replace(staging, target)
        _fsync_dir(snapshots)
        return target


def _kinds(chunks: Sequence[Chunk]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.kind] = counts.get(chunk.kind, 0) + 1
    return counts
