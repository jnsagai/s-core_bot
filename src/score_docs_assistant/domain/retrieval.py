"""Search, lookup and evidence records (specs/004-hybrid-search/data-model.md).

Independent of SQLite, NumPy, FastAPI and Ollama (constitution VI). No field presents a ranking
value as a probability, confidence or correctness measure (FR-011, SC-007).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from score_docs_assistant.domain.snapshots import ChunkKind, SemanticStatus

MatchedBy = Literal["exact", "alias", "keyword", "semantic"]
DegradedReason = Literal[
    "snapshot_lexical_only",
    "embedding_identity_mismatch",
    "embedding_runtime_unavailable",
    "query_too_long_for_embedding",
    "lexical_requested",
]
RANKING_VALUE_DESCRIPTION = (
    "Relative ordering value within this response; not a probability, confidence or measure "
    "of correctness."
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class SearchRequest(BaseModel):
    model_config = _FROZEN

    query: str = Field(min_length=1)
    snapshot_id: str | None = None
    limit: int | None = Field(default=None, ge=1)
    sources: list[str] = []
    kinds: list[ChunkKind] = []


class EvidenceResult(BaseModel):
    model_config = _FROZEN

    rank: int
    chunk_id: str
    snapshot_id: str
    source_id: str
    revision: str
    revision_status: str
    path: str
    origin_path: str
    heading_path: list[str]
    line_start: int | None
    line_end: int | None
    kind: str
    entity_keys: list[str]
    excerpt: str
    truncated: bool
    matched_by: list[MatchedBy]
    ranking_value: float | None = Field(default=None, description=RANKING_VALUE_DESCRIPTION)


class DegradedInfo(BaseModel):
    model_config = _FROZEN

    reason: DegradedReason
    detail: str = ""
    guidance: list[str] = []


class EntitySummary(BaseModel):
    model_config = _FROZEN

    key: str
    need_id: str
    match: Literal["exact", "alias"]
    source_id: str
    revision_status: str
    title: str


class RetrievalSettings(BaseModel):
    model_config = _FROZEN

    fusion_version: int
    lexical_candidates: int
    semantic_candidates: int
    fusion_constant: int
    max_per_document: int


class SearchResponse(BaseModel):
    model_config = _FROZEN

    schema_version: Literal[1] = 1
    snapshot_id: str
    status: Literal["ok", "no_results"]
    mode: Literal["hybrid", "lexical"]
    degraded: DegradedInfo | None
    semantic_status: SemanticStatus
    exact_matches: list[EntitySummary]
    results: list[EvidenceResult]
    warnings: list[str]
    timings_ms: dict[str, float]
    retrieval: RetrievalSettings


class EntityRecord(BaseModel):
    model_config = _FROZEN

    key: str
    need_id: str
    match: Literal["exact", "alias"]
    type: str
    title: str
    status: str | None
    source_id: str
    revision: str | None
    revision_status: str
    path: str
    line_start: int | None
    line_end: int | None
    origin: str
    options: dict[str, str]
    excerpt: str | None
    chunk_id: str | None
    truncated: bool = False


class LookupResponse(BaseModel):
    model_config = _FROZEN

    snapshot_id: str
    query: str
    status: Literal["ok", "no_match"]
    entities: list[EntityRecord]


class Relationship(BaseModel):
    model_config = _FROZEN

    direction: Literal["out", "in"]
    from_key: str
    via: str
    target_id: str
    qualifier: str | None
    resolution: str
    resolved_keys: list[str]
    raw: str


class RelationshipsResponse(BaseModel):
    model_config = _FROZEN

    snapshot_id: str
    key: str
    outgoing_total: int
    incoming_total: int
    limit: int
    offset: int
    items: list[Relationship]


class SnapshotSummary(BaseModel):
    model_config = _FROZEN

    snapshot_id: str
    state: str
    active: bool
    created_at: datetime
    semantic: str | None
    semantic_status: SemanticStatus | None
    chunks: int | None
    documents: int | None
    sources: list[str]
    limitations: list[str]


class SnapshotsResponse(BaseModel):
    model_config = _FROZEN

    active: str | None
    snapshots: list[SnapshotSummary]


class SourceSummary(BaseModel):
    model_config = _FROZEN

    source_id: str
    kind: str
    revision: str | None
    revision_status: str
    required: bool
    status: str
    license_review: list[str]


class SourcesResponse(BaseModel):
    model_config = _FROZEN

    snapshot_id: str
    sources: list[SourceSummary]


class CitationRecord(BaseModel):
    model_config = _FROZEN

    snapshot_id: str
    chunk_id: str
    source_id: str
    revision: str
    revision_status: str
    path: str
    origin_path: str
    heading_path: list[str]
    line_start: int | None
    line_end: int | None
    kind: str
    entity_keys: list[str]
    text: str
    continuation: str | None
