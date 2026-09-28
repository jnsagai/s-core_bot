"""Answer records (specs/005-grounded-chat/data-model.md).

Independent of FastAPI and Ollama types (constitution VI). The envelope is built server-side from
validated claims and stored provenance only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AnswerStatus = Literal["answered", "partial", "insufficient_evidence", "clarification_needed"]
ClaimKind = Literal["documented", "interpretation", "limitation"]
AnswerOrigin = Literal["model", "extractive_fallback", "no_evidence"]
MAX_HISTORY_TURNS = 10

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Turn(BaseModel):
    model_config = _FROZEN

    role: Literal["user", "assistant"]
    content: str = Field(max_length=100_000)
    snapshot_id: str | None = None


class ChatRequest(BaseModel):
    """Validated against configured limits by `AnswerService`; the schema bounds shape."""

    model_config = _FROZEN

    question: str = Field(min_length=1, max_length=100_000)
    snapshot_id: str | None = None
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    response_language: str = "en"


class Claim(BaseModel):
    model_config = _FROZEN

    text: str
    kind: ClaimKind
    evidence_ids: list[str] = []


class Citation(BaseModel):
    model_config = _FROZEN

    evidence_id: str
    chunk_id: str
    snapshot_id: str
    source_id: str
    revision: str
    revision_status: str
    path: str
    heading_path: list[str]
    line_start: int | None
    line_end: int | None
    excerpt: str
    immutable_url: str | None
    revision_match: Literal["exact", "unverified", "none"]


class GenerationIdentity(BaseModel):
    model_config = _FROZEN

    provider: str
    name: str
    digest: str
    runtime_version: str | None = None


class RetrievalSummary(BaseModel):
    model_config = _FROZEN

    mode: str
    degraded_reason: str | None
    results: int
    evidence_supplied: int
    evidence_dropped: int


class AnswerEnvelope(BaseModel):
    model_config = _FROZEN

    schema_version: Literal[1] = 1
    request_id: str
    status: AnswerStatus
    origin: AnswerOrigin
    question: str
    claims: list[Claim]
    limitations: list[str]
    citations: list[Citation]
    snapshot_id: str
    model: GenerationIdentity | None
    retrieval: RetrievalSummary
    warnings: list[str]
    policy_version: int
    timings_ms: dict[str, float]

    @model_validator(mode="after")
    def _citations_cover_claims(self) -> AnswerEnvelope:
        cited = {e for c in self.claims for e in c.evidence_ids}
        if cited != {c.evidence_id for c in self.citations}:
            raise ValueError("every cited evidence ID needs exactly one citation")
        return self
