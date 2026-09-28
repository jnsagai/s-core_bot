"""Snapshot, chunk and bundle records (specs/003-snapshot-index/data-model.md).

Frozen and independent of SQLite, NumPy and Ollama types (constitution VI). Hashed records carry
no floats, so `ingestion/canonical.py` hashes them stably; vectors live only in files.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from score_docs_assistant.ingestion.canonical import canonical_hash

CHUNKER_VERSION = "1"
SNAPSHOT_SCHEMA_VERSION = 1
CORPUS_SCHEMA_VERSION = 1
CATALOG_SCHEMA_VERSION = 1
EMBEDDING_MANIFEST_SCHEMA_VERSION = 1
BUNDLE_FORMAT = 1

ChunkKind = Literal["prose", "need", "table", "code", "literal", "diagram"]
SnapshotState = Literal["building", "validated", "active", "retired", "failed", "deleted"]
Semantic = Literal["present", "absent"]
SemanticStatus = Literal["enabled", "absent", "disabled", "unverified"]
BuildStage = Literal["normalizing", "chunking", "writing", "embedding", "validating", "publishing"]

BUILD_STAGES: tuple[BuildStage, ...] = (
    "normalizing",
    "chunking",
    "writing",
    "embedding",
    "validating",
    "publishing",
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")


def chunk_id(chunker_version: str, document_key: str, ordinal: int, content_hash: str) -> str:
    return canonical_hash(
        {
            "chunker_version": chunker_version,
            "document_key": document_key,
            "ordinal": ordinal,
            "content_hash": content_hash,
        }
    )


class Chunk(BaseModel):
    model_config = _FROZEN

    chunk_id: str
    document_key: str
    ordinal: int
    source_id: str
    revision: str
    path: str
    origin_path: str
    heading_path: list[str]
    kind: ChunkKind
    text: str
    embedding_input: str
    line_start: int | None
    line_end: int | None
    entity_keys: list[str] = []
    need_ids: list[str] = []
    continuation: str | None = None
    table_rows: tuple[int, int] | None = None
    token_estimate: int
    embedding_token_estimate: int
    content_hash: str
    embedding_input_hash: str


class ChunkerConfig(BaseModel):
    model_config = _FROZEN

    chunker_version: str = CHUNKER_VERSION
    min_tokens: int = 350
    max_tokens: int = 700
    overlap_tokens: int = 75
    embedding_max_input_tokens: int = 1800
    prefix_max_tokens: int = 160
    token_count_method: str = "pretoken-v1"
    document_prefix: str = "search_document: "
    prefix_template_version: int = 1

    def sha256(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class EmbeddingIdentity(BaseModel):
    model_config = _FROZEN

    provider: str
    model_tag: str
    model_digest: str
    dimension: int
    preprocessing_revision: str
    normalization: str = "l2-float32"


def preprocessing_revision(config: ChunkerConfig) -> str:
    return canonical_hash(
        {
            "document_prefix": config.document_prefix,
            "prefix_template_version": config.prefix_template_version,
            "truncate": False,
        }
    )


class FileEntry(BaseModel):
    model_config = _FROZEN

    path: str
    sha256: str
    size: int


class ManifestSource(BaseModel):
    model_config = _FROZEN

    source_id: str
    kind: str
    status: str
    required: bool
    revision: str | None
    revision_status: str


class LicenseReviewEntry(BaseModel):
    model_config = _FROZEN

    source_id: str
    path: str
    spdx: str | None


class ManifestCounts(BaseModel):
    model_config = _FROZEN

    documents: int
    entities: int
    relations: int
    chunks: int
    chunks_by_kind: dict[str, int]
    embedded_reused: int = 0
    embedded_new: int = 0


class SourceCoverageSummary(BaseModel):
    model_config = _FROZEN

    source_id: str
    status: str
    selected: int
    included: int
    partial: int
    failed: int
    entities: int


class CoverageSummary(BaseModel):
    model_config = _FROZEN

    sources: list[SourceCoverageSummary]
    limitations: list[str]


class SnapshotManifest(BaseModel):
    model_config = _FROZEN

    schema_version: int
    snapshot_id: str
    created_at: datetime
    app_version: str
    lock_sha256: str
    source_revisions: dict[str, str]
    sources: list[ManifestSource]
    processing_hashes: dict[str, str]
    chunker_version: str
    chunker_config_sha256: str
    token_count_method: str
    semantic: Semantic
    embedding: EmbeddingIdentity | None
    embedding_context_tokens: int | None
    counts: ManifestCounts
    coverage: CoverageSummary
    license_review: list[LicenseReviewEntry]
    corpus_schema_version: int
    files: list[FileEntry]


class EmbeddingManifest(BaseModel):
    model_config = _FROZEN

    schema_version: int
    identity: EmbeddingIdentity
    dtype: Literal["<f4"] = "<f4"
    rows: int
    dimension: int
    file: str = "embeddings.f32"
    sha256: str
    row_chunk_ids: list[str]
    reused_from: dict[str, int] = {}


class CorpusSnapshot(BaseModel):
    model_config = _FROZEN

    snapshot_id: str
    state: SnapshotState
    created_at: datetime
    validated_at: datetime | None = None
    activated_at: datetime | None = None
    retired_at: datetime | None = None
    deleted_at: datetime | None = None
    manifest_sha256: str | None = None
    schema_version: int | None = None
    semantic: Semantic | None = None
    chunks: int | None = None
    job_id: str | None = None
    failure: str | None = None


class ActivationRecord(BaseModel):
    """One row of the catalog's `activation_history` table."""

    model_config = _FROZEN

    seq: int
    snapshot_id: str
    previous_id: str | None
    kind: Literal["activate", "rollback"]
    at: datetime


class BuildJob(BaseModel):
    model_config = _FROZEN

    job_id: str
    kind: Literal["build", "import"]
    state: Literal["running", "succeeded", "failed"]
    pid: int
    started_at: datetime
    finished_at: datetime | None = None
    snapshot_id: str | None = None
    stage: str | None = None
    failure: str | None = None


class Check(BaseModel):
    model_config = _FROZEN

    id: str
    status: Literal["pass", "fail"]
    detail: str = ""


class ValidationReport(BaseModel):
    model_config = _FROZEN

    snapshot_id: str
    checked_at: datetime
    integrity: list[Check]
    integrity_ok: bool
    semantic: SemanticStatus
    semantic_detail: str = ""
    guidance: list[str] = []


class LicenseAcknowledgement(BaseModel):
    model_config = _FROZEN

    reason: str
    files: list[str]


class BundleManifest(BaseModel):
    model_config = _FROZEN

    bundle_format: int
    schema_version: int
    corpus_schema_version: int
    snapshot_id: str
    manifest_sha256: str
    created_at: datetime
    app_version: str
    files: list[FileEntry]
    total_size: int
    entry_count: int
    license_acknowledgement: LicenseAcknowledgement | None = None


class SnapshotHandle(Protocol):
    """A pinned, read-only view of exactly one snapshot (FR-014)."""

    @property
    def snapshot_id(self) -> str: ...

    @property
    def manifest(self) -> SnapshotManifest: ...

    @property
    def directory(self) -> Path: ...

    def corpus(self) -> Any: ...

    def vectors(self) -> Any: ...

    def close(self) -> None: ...


class SnapshotStore(Protocol):
    """Master spec §5.1 interface for pinned snapshot access (consumed by F004)."""

    def list(self, include_deleted: bool = False) -> Sequence[CorpusSnapshot]: ...

    def pin(self, snapshot_id: str) -> SnapshotHandle: ...

    def pin_active(self) -> SnapshotHandle: ...
