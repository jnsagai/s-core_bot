"""Comparison record invariants (specs/007-version-comparison/data-model.md)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from score_docs_assistant.domain.answers import (
    AnswerEnvelope,
    Citation,
    Claim,
    RetrievalSummary,
)
from score_docs_assistant.domain.comparison import (
    ComparisonEvidence,
    ComparisonRequest,
    ComparisonResult,
    Difference,
    SnapshotDiff,
)

LEFT, RIGHT = "20260101T000000Z-aaaaaaaa", "20260202T000000Z-bbbbbbbb"


def citation(evidence_id: str, snapshot_id: str) -> Citation:
    return Citation(
        evidence_id=evidence_id,
        chunk_id="c" * 16,
        snapshot_id=snapshot_id,
        source_id="s",
        revision="a" * 40,
        revision_status="pinned",
        path="docs/x.rst",
        heading_path=["X"],
        line_start=1,
        line_end=2,
        excerpt="text",
        immutable_url=None,
        revision_match="none",
    )


def envelope(snapshot_id: str, citations: list[Citation] | None = None) -> AnswerEnvelope:
    citations = citations or []
    return AnswerEnvelope(
        request_id="r",
        status="answered" if citations else "insufficient_evidence",
        origin="model",
        question="q",
        claims=[Claim(text="t", kind="documented", evidence_ids=[c.evidence_id]) for c in citations]
        or [Claim(text="gap", kind="limitation")],
        limitations=[],
        citations=citations,
        snapshot_id=snapshot_id,
        model=None,
        retrieval=RetrievalSummary(
            mode="hybrid", degraded_reason=None, results=0, evidence_supplied=0, evidence_dropped=0
        ),
        warnings=[],
        policy_version=1,
        timings_ms={},
    )


def diff(left: str = LEFT, right: str = RIGHT) -> SnapshotDiff:
    now = datetime(2026, 9, 29, tzinfo=UTC)
    return SnapshotDiff(
        left_snapshot_id=left,
        right_snapshot_id=right,
        left_created_at=now,
        right_created_at=now,
        sources=[],
        processing=[],
        warnings=[],
    )


def result(**overrides: Any) -> ComparisonResult:
    values: dict[str, Any] = {
        "request_id": "r",
        "question": "q",
        "left": envelope(LEFT),
        "right": envelope(RIGHT),
        "differences": [
            Difference(
                type="changed",
                statement="differs",
                left_evidence_ids=["L1"],
                right_evidence_ids=["R1"],
                origin="model",
            )
        ],
        "evidence": ComparisonEvidence(left=[citation("L1", LEFT)], right=[citation("R1", RIGHT)]),
        "snapshots": diff(),
        "model": None,
        "origin": "model",
        "warnings": [],
        "policy_version": 1,
        "timings_ms": {},
    }
    values.update(overrides)
    return ComparisonResult(**values)


def test_valid_result() -> None:
    assert result().snapshots.release_label is None


def test_request_has_no_history_field() -> None:
    with pytest.raises(ValidationError):
        ComparisonRequest(
            question="q",
            left_snapshot_id=LEFT,
            right_snapshot_id=RIGHT,
            history=[],  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"type": "changed", "left_evidence_ids": ["L1"]}, "both sides"),
        ({"type": "unchanged", "right_evidence_ids": ["R1"]}, "both sides"),
        ({"type": "not_established", "right_evidence_ids": ["R1"]}, "coverage reason"),
        (
            {
                "type": "not_established",
                "right_evidence_ids": ["R1"],
                "coverage_reason": "not_retrieved",
                "missing_side": "right",
            },
            "missing side",
        ),
        (
            {
                "type": "changed",
                "left_evidence_ids": ["L1"],
                "right_evidence_ids": ["R1"],
                "coverage_reason": "not_retrieved",
            },
            "only not_established",
        ),
        ({"type": "changed", "left_evidence_ids": ["R1"], "right_evidence_ids": ["R1"]}, "L<n>"),
    ],
)
def test_difference_rules(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Difference(statement="s", origin="model", **values)


def test_not_established_valid() -> None:
    d = Difference(
        type="not_established",
        statement="Only the right snapshot describes it.",
        right_evidence_ids=["R1"],
        origin="model",
        coverage_reason="not_retrieved",
        missing_side="left",
    )
    assert d.missing_side == "left"


def test_rejects_same_snapshot() -> None:
    with pytest.raises(ValidationError, match="two different"):
        result(
            snapshots=diff(LEFT, LEFT),
            right=envelope(LEFT),
            evidence=ComparisonEvidence(left=[citation("L1", LEFT)], right=[citation("R1", LEFT)]),
        )


def test_rejects_cross_side_citation_in_evidence() -> None:
    with pytest.raises(ValidationError, match="other side"):
        result(
            evidence=ComparisonEvidence(left=[citation("L1", RIGHT)], right=[citation("R1", RIGHT)])
        )


def test_rejects_cross_side_citation_in_envelope() -> None:
    with pytest.raises(ValidationError, match="other side"):
        result(left=envelope(LEFT, [citation("E1", RIGHT)]))


def test_rejects_envelope_bound_to_wrong_snapshot() -> None:
    with pytest.raises(ValidationError, match="bound"):
        result(left=envelope(RIGHT))


def test_rejects_unresolved_difference_id() -> None:
    with pytest.raises(ValidationError, match="resolve"):
        result(
            differences=[
                Difference(
                    type="changed",
                    statement="s",
                    left_evidence_ids=["L2"],
                    right_evidence_ids=["R1"],
                    origin="model",
                )
            ]
        )
