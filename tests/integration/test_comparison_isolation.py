"""Version isolation for comparisons (FR-002, FR-003, SC-001, AT-03; mocked providers)."""

from __future__ import annotations

import json

import pytest

from score_docs_assistant.storage.pins import ExclusiveHold, is_pinned
from tests.helpers.build import app_config
from tests.helpers.comparison_fixtures import (
    ComparisonFixture,
    answer_citing_all,
    make_comparison_fixture,
)
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.fake_generation import FakeGenerationProvider

QUESTIONS = [
    "How many reviewers perform inspections?",
    "How is the documentation build run?",
    "Who writes the release notes?",
    "What does the inspection checklist list?",
    "Compare feat_req__cmp__same and feat_req__cmp__edit",
]


@pytest.fixture
def fx(tmp_path_factory: pytest.TempPathFactory) -> ComparisonFixture:
    return make_comparison_fixture(tmp_path_factory.mktemp("iso"))


@pytest.mark.parametrize("question", QUESTIONS)
def test_zero_cross_side_citations(fx: ComparisonFixture, question: str) -> None:
    result = fx.compare(question, answer_citing_all, answer_citing_all, '{"differences": []}')
    for snapshot_id, citations in (
        (fx.left_id, [*result.left.citations, *result.evidence.left]),
        (fx.right_id, [*result.right.citations, *result.evidence.right]),
    ):
        assert citations, "each side should cite something in these fixtures"
        assert {c.snapshot_id for c in citations} == {snapshot_id}
    # Chunk IDs are content hashes and can repeat across snapshots (unchanged text), so
    # isolation is judged by the snapshot each citation is bound to, never by chunk ID.


def test_activation_mid_comparison_keeps_both_snapshots(fx: ComparisonFixture) -> None:
    from score_docs_assistant.storage import lifecycle

    service = fx.service(generator=FakeGenerationProvider())
    seen: dict[str, bool] = {}

    async def activate_left_and_check_pins() -> None:
        seen["left_pinned"] = is_pinned(fx.data, fx.left_id)
        seen["right_pinned"] = is_pinned(fx.data, fx.right_id)
        lifecycle.activate(
            config=app_config(fx.data),
            snapshot_id=fx.left_id,
            runtime=FakeEmbeddingProvider(),
            progress=lambda _m: None,
        )
        hold = ExclusiveHold.try_acquire(fx.data, fx.right_id)
        seen["right_deletable"] = hold is not None
        if hold is not None:
            hold.release()

    service.after_answers = activate_left_and_check_pins
    generator = service._answers._provider  # noqa: SLF001
    generator.outputs.extend(
        [answer_citing_all, answer_citing_all, json.dumps({"differences": []})]
    )
    result = fx.compare("How many reviewers perform inspections?", service=service)
    assert seen == {"left_pinned": True, "right_pinned": True, "right_deletable": False}
    assert (result.left.snapshot_id, result.right.snapshot_id) == (fx.left_id, fx.right_id)
    assert result.snapshots.left_snapshot_id == fx.left_id
    assert not is_pinned(fx.data, fx.left_id) and not is_pinned(fx.data, fx.right_id)
