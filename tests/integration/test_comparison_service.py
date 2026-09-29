"""ComparisonService over two fixture snapshots (mocked providers; US1, US2, research R1–R5)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from score_docs_assistant.comparison.validate import DELETION_WORDING
from score_docs_assistant.domain.comparison import ComparisonRequest, ComparisonResult
from score_docs_assistant.domain.errors import GenerationError, SearchError
from tests.helpers.comparison_fixtures import (
    LEFT_REV,
    PLATFORM_REV,
    RIGHT_REV,
    ComparisonFixture,
    answer_citing_all,
    differences,
    find,
    make_comparison_fixture,
    side_evidence,
)
from tests.helpers.fake_generation import FakeGenerationProvider


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> ComparisonFixture:
    return make_comparison_fixture(tmp_path_factory.mktemp("cmp"))


@pytest.fixture
def fx(base: ComparisonFixture) -> ComparisonFixture:
    base.generator = FakeGenerationProvider()
    return base


def isolated(result: ComparisonResult) -> None:
    left, right = result.snapshots.left_snapshot_id, result.snapshots.right_snapshot_id
    assert all(c.snapshot_id == left for c in [*result.left.citations, *result.evidence.left])
    assert all(c.snapshot_id == right for c in [*result.right.citations, *result.evidence.right])
    assert not any(DELETION_WORDING.search(d.statement) for d in result.differences)


def changed_script(messages: list[dict[str, str]]) -> str:
    ev = side_evidence(messages)
    return json.dumps(
        differences(
            (
                "changed",
                "The left requires two reviewers; the right requires three.",
                [find(ev, "L", "two independent")],
                [find(ev, "R", "three independent")],
            )
        )
    )


def test_changed_topic(fx: ComparisonFixture) -> None:
    result = fx.compare(
        "How many reviewers perform inspections?",
        answer_citing_all,
        answer_citing_all,
        changed_script,
    )
    isolated(result)
    assert result.origin == "model" and result.model is not None
    assert (result.left.snapshot_id, result.right.snapshot_id) == (fx.left_id, fx.right_id)
    [changed] = [d for d in result.differences if d.origin == "model"]
    assert changed.type == "changed"
    assert len(fx.generator.calls) == 3
    system = fx.generator.calls[2][0]["content"]
    assert "left_evidence_ids" in json.dumps(fx.generator.requests[2]["schema"])
    assert "compare how two snapshots" in system
    assert result.timings_ms["left"] >= 0 and "comparison" in result.timings_ms


def test_unchanged_topic(fx: ComparisonFixture) -> None:
    def script(messages: list[dict[str, str]]) -> str:
        ev = side_evidence(messages)
        return json.dumps(
            differences(
                (
                    "unchanged",
                    "Both describe the documentation build with bazel.",
                    [find(ev, "L", "bazel")],
                    [find(ev, "R", "bazel")],
                )
            )
        )

    result = fx.compare(
        "How is the documentation build run?", answer_citing_all, answer_citing_all, script
    )
    isolated(result)
    assert [d.type for d in result.differences if d.origin == "model"] == ["unchanged"]


def test_conflicting_pair(fx: ComparisonFixture) -> None:
    def script(messages: list[dict[str, str]]) -> str:
        ev = side_evidence(messages)
        return json.dumps(
            differences(
                (
                    "conflicting",
                    "The left assigns release notes to the release manager; the right forbids it.",
                    [find(ev, "L", "release manager before")],
                    [find(ev, "R", "shall not be written")],
                )
            )
        )

    result = fx.compare(
        "Who writes the release notes?", answer_citing_all, answer_citing_all, script
    )
    isolated(result)
    assert [d.type for d in result.differences if d.origin == "model"] == ["conflicting"]


def test_repair_success(fx: ComparisonFixture) -> None:
    bad = json.dumps({"differences": [{"type": "changed"}]})
    result = fx.compare(
        "How many reviewers perform inspections?",
        answer_citing_all,
        answer_citing_all,
        bad,
        changed_script,
    )
    assert result.origin == "model"
    assert any(w.startswith("repaired:") for w in result.warnings)
    assert "failed these checks" in fx.generator.calls[3][-1]["content"]


def test_repair_failure_gives_deterministic_only(fx: ComparisonFixture) -> None:
    bad = "not json"
    result = fx.compare(
        "What does feat_req__cmp__edit require?", answer_citing_all, answer_citing_all, bad, bad
    )
    isolated(result)
    assert result.origin == "deterministic_only"
    assert any(w.startswith("comparison_output_invalid") for w in result.warnings)
    assert result.differences and all(d.origin != "model" for d in result.differences)


def test_deletion_claim_is_never_returned(fx: ComparisonFixture) -> None:
    def removed(messages: list[dict[str, str]]) -> str:
        ev = side_evidence(messages)
        return json.dumps(
            differences(
                (
                    "not_established",
                    "The checklist was removed from the left snapshot.",
                    [],
                    [find(ev, "R", "checklist")],
                )
            )
        )

    result = fx.compare(
        "What does the inspection checklist list?",
        answer_citing_all,
        answer_citing_all,
        removed,
        removed,
    )
    isolated(result)
    assert result.origin == "deterministic_only"
    assert "DELETION_CLAIM" in result.warnings[-1]


def test_one_sided_model_difference_gets_server_reason(fx: ComparisonFixture) -> None:
    def script(messages: list[dict[str, str]]) -> str:
        ev = side_evidence(messages)
        return json.dumps(
            differences(
                (
                    "not_established",
                    "Only the right snapshot describes how the orchestrator schedules the gateway.",
                    [],
                    [find(ev, "R", "orchestrator")],
                )
            )
        )

    result = fx.compare(
        "How does the orchestrator schedule the gateway?",
        answer_citing_all,
        answer_citing_all,
        script,
    )
    isolated(result)
    [d] = [d for d in result.differences if d.origin == "model"]
    assert (d.missing_side, d.coverage_reason) == ("left", "source_absent")


def test_side_without_evidence_skips_model_step(fx: ComparisonFixture) -> None:
    fx.provider.query_mode = "unreachable"  # keyword-only, so an unmatched side has no evidence
    try:
        result = fx.compare("orchestrator", answer_citing_all, answer_citing_all)
    finally:
        fx.provider.query_mode = "ok"
    isolated(result)
    assert result.evidence.left == [] and result.left.status == "insufficient_evidence"
    coverage = [d for d in result.differences if d.origin == "coverage"]
    assert coverage and coverage[0].missing_side == "left"
    assert coverage[0].coverage_reason == "no_evidence"
    assert all(d.type == "not_established" for d in result.differences)
    assert len(fx.generator.calls) == 1  # only the right side's answer
    assert result.origin == "deterministic_only"


def test_exact_records(fx: ComparisonFixture) -> None:
    result = fx.compare(
        "Compare feat_req__cmp__same, feat_req__cmp__edit, feat_req__cmp__new and "
        "feat_req__cmp__plat",
        answer_citing_all,
        answer_citing_all,
        json.dumps({"differences": []}),
    )
    isolated(result)
    records = {d.statement.split()[0]: d for d in result.differences if d.origin == "exact_record"}
    assert records["feat_req__cmp__same"].type == "unchanged"
    edit = records["feat_req__cmp__edit"]
    assert edit.type == "changed" and "title" in edit.statement and "text" in edit.statement
    new = records["feat_req__cmp__new"]
    assert (new.type, new.missing_side, new.coverage_reason) == (
        "not_established",
        "left",
        "record_not_found",
    )
    plat = records["feat_req__cmp__plat"]
    assert (plat.missing_side, plat.coverage_reason) == ("left", "source_absent")
    assert "does not show that it changed or disappeared" in plat.statement


def test_side_with_extractive_fallback(fx: ComparisonFixture) -> None:
    result = fx.compare(
        "How many reviewers perform inspections?",
        "garbage",
        "garbage",
        answer_citing_all,
        changed_script,
    )
    isolated(result)
    assert result.left.origin == "extractive_fallback"
    assert result.origin == "model"


def test_degraded_retrieval_is_reported_per_side(fx: ComparisonFixture) -> None:
    fx.provider.query_mode = "unreachable"
    try:
        result = fx.compare(
            "How many reviewers perform inspections?",
            answer_citing_all,
            answer_citing_all,
            changed_script,
        )
    finally:
        fx.provider.query_mode = "ok"
    isolated(result)
    for envelope in (result.left, result.right):
        assert envelope.retrieval.degraded_reason == "embedding_runtime_unavailable"


@pytest.mark.parametrize(
    ("left", "right", "code"),
    [("same", "same", "REQUEST_INVALID"), ("bad id", None, "REQUEST_INVALID")],
)
def test_request_validation(fx: ComparisonFixture, left: str, right: str | None, code: str) -> None:
    left_id = fx.left_id if left == "same" else left
    right_id = fx.left_id if right == "same" else (right or fx.right_id)
    with pytest.raises(GenerationError) as info:
        fx.compare("q", left=left_id, right=right_id)
    assert info.value.code == code
    assert fx.generator.calls == []


def test_unknown_snapshot(fx: ComparisonFixture) -> None:
    with pytest.raises(SearchError) as info:
        fx.compare("q", right="20990101T000000Z-deadbeef")
    assert info.value.code == "SNAPSHOT_NOT_FOUND"


def test_generation_unavailable_fails_fast(fx: ComparisonFixture) -> None:
    fx.generator.unavailable = "runtime_unreachable"
    with pytest.raises(GenerationError) as info:
        fx.compare("How many reviewers perform inspections?")
    assert info.value.code == "GENERATION_UNAVAILABLE"


def test_deadline(fx: ComparisonFixture) -> None:
    fx.generator.delay = 2.0
    service = fx.service(comparison={"deadline_seconds": 1})
    with pytest.raises(GenerationError) as info:
        fx.compare("How many reviewers perform inspections?", service=service)
    assert info.value.code == "DEADLINE_EXCEEDED"


def test_answer_in_slot_does_not_touch_the_queue(fx: ComparisonFixture) -> None:
    from score_docs_assistant.domain.answers import ChatRequest

    service = fx.service()
    answers: Any = service._answers  # noqa: SLF001
    fx.generator.outputs.append(answer_citing_all)

    async def run() -> None:
        async with answers.queue.slot(None):  # hold the only slot
            loop = asyncio.get_running_loop()
            envelope, items = await answers.answer_in_slot(
                ChatRequest(question="How many reviewers?", snapshot_id=fx.left_id),
                request_id="t",
                deadline=loop.time() + 30,
            )
            assert envelope.snapshot_id == fx.left_id and items

    asyncio.run(run())


def test_request_model_rejects_history() -> None:
    with pytest.raises(ValueError):
        ComparisonRequest.model_validate(
            {"question": "q", "left_snapshot_id": "a", "right_snapshot_id": "b", "history": []}
        )


def test_citation_links_for_archived_left_revision(fx: ComparisonFixture) -> None:
    result = fx.compare(
        "How many reviewers perform inspections?",
        answer_citing_all,
        answer_citing_all,
        changed_script,
    )
    # The left revision is only in the archived lock (research R7); links stay exact per side.
    assert result.evidence.left and result.evidence.right
    assert all(f"/blob/{LEFT_REV}/" in (c.immutable_url or "") for c in result.evidence.left)
    assert all(f"/blob/{c.revision}/" in (c.immutable_url or "") for c in result.evidence.right)
    assert {c.revision for c in result.evidence.right} <= {RIGHT_REV, PLATFORM_REV}
    assert all(c.revision_match == "exact" for c in result.evidence.left + result.evidence.right)
