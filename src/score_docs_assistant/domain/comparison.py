"""Comparison records (specs/007-version-comparison/data-model.md).

Invariants are checked on construction so a result can never carry a citation from the wrong
snapshot, a difference whose evidence does not resolve on its side, or an absence stated as a
typed change.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from score_docs_assistant.domain.answers import AnswerEnvelope, Citation, GenerationIdentity

DifferenceType = Literal["changed", "unchanged", "conflicting", "not_established"]
DifferenceOrigin = Literal["model", "exact_record", "coverage"]
CoverageReason = Literal[
    "source_absent",
    "source_failed",
    "source_partial",
    "record_not_found",
    "record_without_excerpt",
    "not_retrieved",
    "no_evidence",
]
Side = Literal["left", "right"]
MissingSide = Literal["left", "right", "both"]
SourceRelationKind = Literal["same", "different", "left_only", "right_only"]
ComparisonOrigin = Literal["model", "deterministic_only"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")
LEFT_ID = re.compile(r"^L[0-9]{1,3}$")
RIGHT_ID = re.compile(r"^R[0-9]{1,3}$")


class ComparisonRequest(BaseModel):
    model_config = _FROZEN

    question: str = Field(min_length=1, max_length=100_000)
    left_snapshot_id: str
    right_snapshot_id: str
    response_language: str = "en"


class Difference(BaseModel):
    model_config = _FROZEN

    type: DifferenceType
    statement: str
    left_evidence_ids: list[str] = []
    right_evidence_ids: list[str] = []
    origin: DifferenceOrigin
    coverage_reason: CoverageReason | None = None
    missing_side: MissingSide | None = None

    @model_validator(mode="after")
    def _type_rules(self) -> Difference:
        if any(not LEFT_ID.match(e) for e in self.left_evidence_ids) or any(
            not RIGHT_ID.match(e) for e in self.right_evidence_ids
        ):
            raise ValueError("evidence IDs must be L<n> on the left and R<n> on the right")
        if self.type == "not_established":
            if self.coverage_reason is None or self.missing_side is None:
                raise ValueError("not_established needs a coverage reason and a missing side")
            if self.missing_side in ("left", "both") and self.left_evidence_ids:
                raise ValueError("the missing side cannot cite evidence")
            if self.missing_side in ("right", "both") and self.right_evidence_ids:
                raise ValueError("the missing side cannot cite evidence")
        else:
            if not self.left_evidence_ids or not self.right_evidence_ids:
                raise ValueError(f"{self.type} needs evidence on both sides")
            if self.coverage_reason is not None or self.missing_side is not None:
                raise ValueError("only not_established carries a coverage reason")
        return self


class SourceRelation(BaseModel):
    model_config = _FROZEN

    source_id: str
    relation: SourceRelationKind
    left_revision: str | None
    right_revision: str | None
    left_revision_status: str | None
    right_revision_status: str | None
    left_status: str | None
    right_status: str | None


class ProcessingDifference(BaseModel):
    model_config = _FROZEN

    field: str
    left: str | None
    right: str | None


class SnapshotDiff(BaseModel):
    model_config = _FROZEN

    left_snapshot_id: str
    right_snapshot_id: str
    left_created_at: datetime
    right_created_at: datetime
    sources: list[SourceRelation]
    processing: list[ProcessingDifference]
    release_label: None = None  # never inferred (SRC-003, research R6)
    warnings: list[str]


class ComparisonEvidence(BaseModel):
    model_config = _FROZEN

    left: list[Citation] = []
    right: list[Citation] = []


class ComparisonResult(BaseModel):
    model_config = _FROZEN

    schema_version: Literal[1] = 1
    request_id: str
    question: str
    left: AnswerEnvelope
    right: AnswerEnvelope
    differences: list[Difference]
    evidence: ComparisonEvidence
    snapshots: SnapshotDiff
    model: GenerationIdentity | None
    origin: ComparisonOrigin
    warnings: list[str]
    policy_version: int
    timings_ms: dict[str, float]

    @model_validator(mode="after")
    def _isolation(self) -> ComparisonResult:
        left_id, right_id = self.snapshots.left_snapshot_id, self.snapshots.right_snapshot_id
        if left_id == right_id:
            raise ValueError("a comparison needs two different snapshots")
        if self.left.snapshot_id != left_id or self.right.snapshot_id != right_id:
            raise ValueError("each envelope must be bound to its side's snapshot")
        for side_id, citations in (
            (left_id, [*self.left.citations, *self.evidence.left]),
            (right_id, [*self.right.citations, *self.evidence.right]),
        ):
            if any(c.snapshot_id != side_id for c in citations):
                raise ValueError("a citation references the other side's snapshot")
        left_ids = {c.evidence_id for c in self.evidence.left}
        right_ids = {c.evidence_id for c in self.evidence.right}
        if len(left_ids) != len(self.evidence.left) or len(right_ids) != len(self.evidence.right):
            raise ValueError("duplicate comparison evidence IDs")
        for difference in self.differences:
            if (
                not set(difference.left_evidence_ids) <= left_ids
                or not set(difference.right_evidence_ids) <= right_ids
            ):
                raise ValueError("a difference cites evidence that does not resolve on its side")
        return self
