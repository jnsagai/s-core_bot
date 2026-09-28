"""AnswerService end to end with fake providers (FR-001–FR-009, FR-014; SC-001–SC-003). Mocked."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.domain.answers import AnswerEnvelope
from score_docs_assistant.domain.errors import GenerationError
from score_docs_assistant.storage.corpus_db import open_corpus_readonly
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import FakeGenerationProvider, answer


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("answers"))


def assert_citation_integrity(fx: AnswerFixture, envelope: AnswerEnvelope) -> None:
    """SC-001: every citation resolves to the pinned snapshot and its stored text."""
    corpus = fx.data / "snapshots" / envelope.snapshot_id / "corpus.sqlite"
    conn = open_corpus_readonly(corpus)
    try:
        for citation in envelope.citations:
            assert citation.snapshot_id == envelope.snapshot_id
            row = conn.execute(
                "SELECT text, path, source_id FROM chunks WHERE chunk_id = ?", (citation.chunk_id,)
            ).fetchone()
            assert row is not None
            assert row[0].startswith(citation.excerpt.rstrip())
            assert (row[1], row[2]) == (citation.path, citation.source_id)
    finally:
        conn.close()


def test_answered_envelope(fx: AnswerFixture) -> None:
    envelope = fx.ask(
        "What does feat_req__alpha__long require?",
        answer(
            "answered",
            ("The long requirement describes persistence of configuration.", "documented", ["E1"]),
            ("This suggests configuration must survive restarts.", "interpretation", ["E1"]),
        ),
    )
    assert envelope.status == "answered" and envelope.origin == "model"
    assert envelope.snapshot_id == fx.search.snapshot_id
    assert envelope.model is not None and envelope.model.name == "qwen3:4b-instruct"
    assert [c.kind for c in envelope.claims] == ["documented", "interpretation"]
    assert [c.evidence_id for c in envelope.citations] == ["E1"]
    assert envelope.citations[0].path == "docs/reqs.rst"
    assert envelope.retrieval.mode == "hybrid" and envelope.retrieval.evidence_supplied > 0
    assert envelope.policy_version == 1
    assert set(envelope.timings_ms) >= {"queue", "retrieval", "generation", "total"}
    assert_citation_integrity(fx, envelope)


def test_prompt_sent_to_model(fx: AnswerFixture) -> None:
    generator = FakeGenerationProvider(
        outputs=[answer("insufficient_evidence", ("No info.", "limitation", []))]
    )
    fx.ask("watchdog deadlines", service=fx.service(generator))
    [messages] = generator.calls
    assert messages[0]["role"] == "system" and "untrusted" in messages[0]["content"]
    assert "<evidence>" in messages[1]["content"] and "watchdog" in messages[1]["content"]
    request = generator.requests[0]
    assert request["temperature"] == 0.1 and request["num_ctx"] == 8192
    assert request["num_predict"] == 900 and request["schema"]["required"] == ["status", "claims"]


def test_commands_stay_text(fx: AnswerFixture) -> None:
    envelope = fx.ask(
        "How do I build the documentation?",
        lambda messages: __import__("json").dumps(
            answer(
                "answered",
                (
                    "Run `bazel run //:docs` to build the documentation.",
                    "documented",
                    [
                        next(
                            iter(
                                __import__("tests.helpers.answers", fromlist=["x"]).evidence_ids(
                                    messages
                                )
                            )
                        )
                    ],
                ),
            )
        ),
    )
    assert envelope.status == "answered"
    assert "`bazel run //:docs`" in envelope.claims[0].text


def test_snapshot_activated_during_generation_keeps_original(tmp_path: Path) -> None:
    from tests.helpers.build import build
    from tests.helpers.lifecycle import activate

    local = make_answer_fixture(tmp_path)
    other = build(local.search.env, local.search.provider, write_lock=False).snapshot_id
    service = local.service()

    async def switch() -> None:
        activate(local.search.env, other, runtime=local.search.provider)

    service.after_retrieval = switch
    envelope = local.ask(
        "watchdog",
        answer("answered", ("The watchdog supervises task deadlines.", "documented", ["E1"])),
        service=service,
    )
    assert envelope.snapshot_id == local.search.snapshot_id != other
    assert all(c.snapshot_id == local.search.snapshot_id for c in envelope.citations)
    assert_citation_integrity(local, envelope)


def test_request_validation(fx: AnswerFixture) -> None:
    for kwargs, code in (
        ({"response_language": "de"}, "UNSUPPORTED_LANGUAGE"),
        ({"snapshot_id": "../x"}, "REQUEST_INVALID"),
        ({"history": [{"role": "user", "content": "x" * 13000}]}, "REQUEST_INVALID"),
    ):
        with pytest.raises(GenerationError) as exc_info:
            fx.ask("q", **kwargs)
        assert exc_info.value.code == code
    with pytest.raises(GenerationError):
        fx.ask("x" * 4001)


# --- US2: honest failure modes ----------------------------------------------------------------


def test_no_evidence_skips_the_model(fx: AnswerFixture) -> None:
    from tests.helpers.fake_embedding import FakeEmbeddingProvider

    generator = FakeGenerationProvider()
    service = fx.service(generator, FakeEmbeddingProvider(mode="unreachable"))
    envelope = fx.ask("xyzzyplugh", service=service)
    assert envelope.status == "insufficient_evidence" and envelope.origin == "no_evidence"
    assert generator.calls == [] and envelope.model is None
    assert [c.kind for c in envelope.claims] == ["limitation"] and envelope.citations == []


def test_invalid_then_repaired(fx: AnswerFixture) -> None:
    generator = FakeGenerationProvider(
        outputs=[
            answer("answered", ("Uses a fake source.", "documented", ["E99"])),
            answer("answered", ("The watchdog supervises task deadlines.", "documented", ["E1"])),
        ]
    )
    envelope = fx.ask("watchdog", service=fx.service(generator))
    assert envelope.status == "answered" and envelope.origin == "model"
    assert any(w.startswith("repaired") for w in envelope.warnings)
    assert len(generator.calls) == 2
    assert "UNKNOWN_EVIDENCE_ID" in generator.calls[1][-1]["content"]
    assert_citation_integrity(fx, envelope)


@pytest.mark.parametrize(
    "bad",
    [
        "not json at all",
        answer("answered", ("Nothing documented here.", "limitation", [])),
        answer("answered", ("Details at https://evil.example/", "documented", ["E1"])),
        answer(
            "answered", ('It says "the gateway is certified for ASIL D".', "documented", ["E1"])
        ),
    ],
)
def test_invalid_twice_falls_back_to_excerpts(fx: AnswerFixture, bad: object) -> None:
    generator = FakeGenerationProvider(outputs=[bad, bad])  # type: ignore[list-item]
    envelope = fx.ask("watchdog", service=fx.service(generator))
    assert envelope.status == "partial" and envelope.origin == "extractive_fallback"
    assert any(w.startswith("model_output_invalid") for w in envelope.warnings)
    documented = [c for c in envelope.claims if c.kind == "documented"]
    assert 1 <= len(documented) <= 3
    for claim, citation in zip(documented, envelope.citations, strict=True):
        assert citation.excerpt.startswith(claim.text.rstrip())  # verbatim stored text only
    assert "evil.example" not in envelope.model_dump_json()
    assert_citation_integrity(fx, envelope)


def test_no_repair_when_deadline_is_short(fx: AnswerFixture) -> None:
    generator = FakeGenerationProvider(outputs=["bad", answer("answered")])
    service = fx.service(generator, generation={"repair_min_seconds": 600})
    envelope = fx.ask("watchdog", service=service)
    assert envelope.origin == "extractive_fallback" and len(generator.calls) == 1


@pytest.mark.parametrize(
    ("generator", "reason"),
    [
        (FakeGenerationProvider(unavailable="runtime_unreachable"), "runtime_unreachable"),
        (FakeGenerationProvider(unavailable="model_missing"), "model_missing"),
        (FakeGenerationProvider(digest="9" * 64), "model_identity_mismatch"),
    ],
)
def test_generation_unavailable_keeps_search(
    fx: AnswerFixture, generator: FakeGenerationProvider, reason: str
) -> None:
    with pytest.raises(GenerationError) as exc_info:
        fx.ask("watchdog", service=fx.service(generator))
    assert exc_info.value.code == "GENERATION_UNAVAILABLE" and exc_info.value.reason == reason
    from score_docs_assistant.domain.retrieval import SearchRequest

    assert fx.search.service().search(SearchRequest(query="watchdog")).results


def test_missing_lock_entry_is_unavailable(tmp_path: Path) -> None:
    from tests.helpers.snapshot_env import write_model_lock

    local = make_answer_fixture(tmp_path)
    write_model_lock(local.data, local.search.provider.digest)  # embedding only
    with pytest.raises(GenerationError) as exc_info:
        local.ask("watchdog")
    assert exc_info.value.reason == "model_not_locked"


def test_deadline(fx: AnswerFixture) -> None:
    generator = FakeGenerationProvider(delay=5)
    service = fx.service(generator, limits={"request_deadline_seconds": 1})
    with pytest.raises(GenerationError) as exc_info:
        fx.ask("watchdog", service=service)
    assert exc_info.value.code == "DEADLINE_EXCEEDED" and exc_info.value.retryable
    assert generator.cancelled == 1
    assert not service.queue.active


def test_history_and_follow_up(fx: AnswerFixture) -> None:
    generator = FakeGenerationProvider(
        outputs=[answer("insufficient_evidence", ("No.", "limitation", []))]
    )
    envelope = fx.ask(
        "and the deadlines?",
        service=fx.service(generator),
        history=[
            {"role": "user", "content": "tell me about the watchdog"},
            {
                "role": "assistant",
                "content": "old answer",
                "snapshot_id": "20200101T000000Z-00000000",
            },
        ],
    )
    assert any(w.startswith("new_evidence_context") for w in envelope.warnings)
    assert "old answer" not in generator.calls[0][1]["content"]


def test_insufficient_without_claims_gets_server_limitation(fx: AnswerFixture) -> None:
    envelope = fx.ask("watchdog", answer("insufficient_evidence"))
    assert envelope.status == "insufficient_evidence"
    assert envelope.limitations == ["The supplied evidence does not answer this question."]
    assert envelope.citations == []
