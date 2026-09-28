"""Answer records and GenerationError (data-model.md)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from score_docs_assistant.domain.answers import (
    AnswerEnvelope,
    ChatRequest,
    Citation,
    Claim,
    RetrievalSummary,
)
from score_docs_assistant.domain.errors import GenerationError


def test_chat_request_shape() -> None:
    request = ChatRequest(question="q", history=[{"role": "user", "content": "a"}])  # type: ignore[list-item]
    assert request.response_language == "en"
    for bad in (
        {"question": ""},
        {"question": "q", "model": "x"},
        {"question": "q", "system_prompt": "x"},
        {"question": "q", "history": [{"role": "system", "content": "x"}]},
        {"question": "q", "history": [{"role": "user", "content": "x"}] * 11},
    ):
        with pytest.raises(ValidationError):
            ChatRequest.model_validate(bad)


def _citation(eid: str) -> Citation:
    return Citation(
        evidence_id=eid,
        chunk_id="c",
        snapshot_id="s",
        source_id="a",
        revision="r",
        revision_status="pinned",
        path="p",
        heading_path=[],
        line_start=1,
        line_end=2,
        excerpt="x",
        immutable_url=None,
        revision_match="none",
    )


def _envelope(claims: list[Claim], citations: list[Citation]) -> AnswerEnvelope:
    return AnswerEnvelope(
        request_id="r",
        status="answered",
        origin="model",
        question="q",
        claims=claims,
        limitations=[],
        citations=citations,
        snapshot_id="s",
        model=None,
        retrieval=RetrievalSummary(
            mode="hybrid", degraded_reason=None, results=1, evidence_supplied=1, evidence_dropped=0
        ),
        warnings=[],
        policy_version=1,
        timings_ms={},
    )


def test_envelope_citations_must_match_cited_ids() -> None:
    claim = Claim(text="t", kind="documented", evidence_ids=["E1"])
    assert _envelope([claim], [_citation("E1")]).citations[0].evidence_id == "E1"
    with pytest.raises(ValidationError):
        _envelope([claim], [])
    with pytest.raises(ValidationError):
        _envelope([claim], [_citation("E1"), _citation("E2")])


@pytest.mark.parametrize(
    ("code", "status", "retryable"),
    [
        ("GENERATION_UNAVAILABLE", 503, True),
        ("CHAT_BUSY", 429, True),
        ("DEADLINE_EXCEEDED", 504, True),
        ("ANSWER_INVALID", 502, False),
        ("UNSUPPORTED_LANGUAGE", 422, False),
    ],
)
def test_generation_error(code: str, status: int, retryable: bool) -> None:
    error = GenerationError(code, "m", reason="x")
    assert (error.http_status, error.retryable, error.reason) == (status, retryable, "x")
    with pytest.raises(ValueError):
        GenerationError("NOPE", "m")
