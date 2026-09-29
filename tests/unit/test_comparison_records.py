"""Exact-record comparison (FR-011, research R5b)."""

from __future__ import annotations

import pytest

from score_docs_assistant.comparison.records import RecordPair, compare_records
from score_docs_assistant.domain.comparison import Difference
from score_docs_assistant.retrieval.service import SearchService
from tests.helpers.comparison_fixtures import ComparisonFixture, make_comparison_fixture


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> ComparisonFixture:
    return make_comparison_fixture(tmp_path_factory.mktemp("rec"))


def _pairs(fx: ComparisonFixture, question: str) -> dict[str, RecordPair]:
    search = SearchService(config=fx.config(), provider=fx.provider)
    with search.pinned(fx.left_id) as a, search.pinned(fx.right_id) as b:
        pairs = compare_records(
            question,
            (search.entity_index(a), a.corpus()),
            (search.entity_index(b), b.corpus()),
        )
    return {p.need_id: p for p in pairs}


def test_verdicts(fx: ComparisonFixture) -> None:
    pairs = _pairs(
        fx, "feat_req__cmp__new then feat_req__cmp__same, feat_req__cmp__edit, feat_req__nope"
    )
    assert list(pairs) == ["feat_req__cmp__new", "feat_req__cmp__same", "feat_req__cmp__edit"]
    assert pairs["feat_req__cmp__same"].verdict == "unchanged"
    assert pairs["feat_req__cmp__same"].changed_fields == ()
    assert pairs["feat_req__cmp__edit"].verdict == "changed"
    assert pairs["feat_req__cmp__edit"].changed_fields == ("title", "text")
    assert pairs["feat_req__cmp__new"].verdict == "right_only"
    assert pairs["feat_req__cmp__new"].left is None


def test_location_only_change_is_not_a_change(fx: ComparisonFixture) -> None:
    pairs = _pairs(fx, "feat_req__cmp__edit")
    edit = pairs["feat_req__cmp__edit"]
    assert edit.left is not None and edit.right is not None
    moved = edit.right.model_copy(
        update={
            "line_start": 99,
            "line_end": 120,
            "title": edit.left.title,
            "excerpt": edit.left.excerpt,
        }
    )
    from score_docs_assistant.comparison.records import _changed_fields

    assert _changed_fields(edit.left, moved) == ()


def test_no_ids_no_pairs(fx: ComparisonFixture) -> None:
    assert _pairs(fx, "How are inspections performed?") == {}


def test_record_without_excerpt_is_not_established(fx: ComparisonFixture) -> None:
    from score_docs_assistant.comparison.service import ComparisonService, _Side

    service: ComparisonService = fx.service()
    pair = _pairs(fx, "feat_req__cmp__same")["feat_req__cmp__same"]
    assert pair.right is not None
    no_chunk = RecordPair(
        pair.need_id, pair.left, pair.right.model_copy(update={"chunk_id": None}), "unchanged"
    )
    search = SearchService(config=fx.config(), provider=fx.provider)
    with search.pinned(fx.left_id) as a, search.pinned(fx.right_id) as b:
        [difference] = service._record_differences(  # noqa: SLF001
            [no_chunk], {"left": _Side("L"), "right": _Side("R")}, a, b
        )
    assert isinstance(difference, Difference)
    assert (difference.type, difference.coverage_reason, difference.missing_side) == (
        "not_established",
        "record_without_excerpt",
        "right",
    )
    assert difference.right_evidence_ids == [] and difference.left_evidence_ids == ["L1"]
