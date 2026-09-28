"""Draft validation codes (FR-003, FR-005, FR-007, contracts/answer-schema.md, research R4)."""

from __future__ import annotations

import json

import pytest

from score_docs_assistant.answers.prompt import EvidenceItem, escape
from score_docs_assistant.answers.validate import MAX_RAW_BYTES, validate_draft
from score_docs_assistant.domain.retrieval import EvidenceResult

EXCERPT = "The architecture shall use <static> views. Run `bazel build //:docs` to build it."


def _evidence() -> dict[str, EvidenceItem]:
    items = {}
    for i in (1, 2):
        result = EvidenceResult.model_validate(
            dict(
                rank=i,
                chunk_id=f"{i:064x}",
                snapshot_id="s",
                source_id="a",
                revision="r",
                revision_status="pinned",
                path="p",
                origin_path="p",
                heading_path=[],
                line_start=1,
                line_end=2,
                kind="prose",
                entity_keys=[],
                excerpt=EXCERPT,
                truncated=False,
                matched_by=["keyword"],
            )
        )
        items[f"E{i}"] = EvidenceItem(f"E{i}", result, escape(EXCERPT), 10)
    return items


def _check(draft: object, truncated: bool = False) -> list[str]:
    raw = draft if isinstance(draft, str) else json.dumps(draft)
    outcome = validate_draft(
        raw, truncated=truncated, evidence=_evidence(), max_claims=12, max_claim_characters=1200
    )
    return [e.split(":")[0] for e in outcome.errors]


def _draft(status: str, *claims: tuple[str, str, list[str]]) -> dict:  # type: ignore[type-arg]
    return {
        "status": status,
        "claims": [{"text": t, "kind": k, "evidence_ids": e} for t, k, e in claims],
    }


DOC = ("The architecture uses static views.", "documented", ["E1"])
LIM = ("The evidence does not cover components.", "limitation", [])


@pytest.mark.parametrize(
    ("draft", "status"),
    [
        (_draft("answered", DOC), "answered"),
        (_draft("partial", DOC, LIM), "partial"),
        (_draft("insufficient_evidence", LIM), "insufficient_evidence"),
        (_draft("clarification_needed", LIM), "clarification_needed"),
        (
            _draft("answered", DOC, ("My reading: static first.", "interpretation", ["E2"])),
            "answered",
        ),
    ],
)
def test_valid_drafts(draft: dict, status: str) -> None:  # type: ignore[type-arg]
    assert _check(draft) == []


@pytest.mark.parametrize(
    ("draft", "code"),
    [
        ("not json", "JSON_INVALID"),
        ("[1, 2]", "JSON_INVALID"),
        ({"status": "answered"}, None),  # claims default to empty → STATUS_INCONSISTENT
        ({"status": "done", "claims": []}, "SCHEMA_INVALID"),
        ({"status": "answered", "claims": [], "extra": 1}, "SCHEMA_INVALID"),
        (_draft("answered", ("t", "fact", ["E1"])), "SCHEMA_INVALID"),
        (_draft("answered", ("Uses static views.", "documented", ["E9"])), "UNKNOWN_EVIDENCE_ID"),
        (_draft("answered", ("Uses static views.", "documented", [])), "MISSING_CITATION"),
        (_draft("answered", DOC, ("Reading.", "interpretation", [])), "MISSING_CITATION"),
        (_draft("insufficient_evidence", DOC), "STATUS_INCONSISTENT"),  # observed on the real model
        (_draft("answered", LIM), "STATUS_INCONSISTENT"),
        (_draft("partial", DOC), "STATUS_INCONSISTENT"),
        (
            _draft(
                "answered",
                ('It says "the platform is fully certified today".', "documented", ["E1"]),
            ),
            "QUOTE_NOT_IN_EVIDENCE",
        ),
        (
            _draft("answered", ("See https://evil.example/x for details.", "documented", ["E1"])),
            "URL_IN_TEXT",
        ),
        (
            _draft("answered", ("<think>hmm</think> static views", "documented", ["E1"])),
            "HIDDEN_THOUGHT",
        ),
        (_draft("answered", DOC, ("   ", "limitation", [])), "EMPTY_CLAIM"),
    ],
)
def test_invalid_drafts(draft: object, code: str | None) -> None:
    codes = _check(draft)
    assert codes, draft
    assert (code or "STATUS_INCONSISTENT") in codes


def test_quotes_match_stored_or_escaped_text_and_short_quotes_exempt() -> None:
    ok = [
        ("Run `bazel build //:docs` to build it.", "documented", ["E1"]),
        ('It "shall use <static> views" per E1.', "documented", ["E1"]),
        ('It "shall use ‹static› views" per E1.', "documented", ["E1"]),
        ('The "id" field is short.', "documented", ["E1"]),
    ]
    for claim in ok:
        assert _check(_draft("answered", claim)) == [], claim


def test_truncated_and_oversized_output() -> None:
    assert _check(_draft("answered", DOC), truncated=True) == ["JSON_INVALID"]
    assert _check("x" * (MAX_RAW_BYTES + 1)) == ["JSON_INVALID"]


def test_too_many_claims() -> None:
    assert "SCHEMA_INVALID" in _check(_draft("answered", *([DOC] * 13)))
