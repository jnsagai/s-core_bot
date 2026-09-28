"""Exact-first RRF fusion, dedup, caps, tie-breaks (FR-009, FR-010, research R4)."""

from __future__ import annotations

import pytest

from score_docs_assistant.retrieval.fusion import ChunkMeta, fuse


def _meta(**rows: tuple[str, str, int, str]) -> dict[int, ChunkMeta]:
    return {
        int(k[1:]): ChunkMeta(document_key=d, source_id=s, ordinal=o, content_hash=h)
        for k, (d, s, o, h) in rows.items()
    }


META = _meta(
    r1=("d1", "a", 0, "h1"),
    r2=("d1", "a", 1, "h2"),
    r3=("d1", "a", 2, "h3"),
    r4=("d1", "a", 3, "h4"),
    r5=("d2", "a", 0, "h1"),  # same text as r1, same source → deduplicated
    r6=("d3", "b", 0, "h1"),  # same text as r1, other source → kept
    r7=("d4", "a", 0, "h7"),
)


def test_rrf_values_and_order() -> None:
    selected = fuse([], [7, 2], [2, 7], META, constant=60, limit=10, per_document=3)
    assert [s.rowid for s in selected] == [2, 7]  # tie in RRF → document_key d1 < d4
    assert selected[0].ranking_value == pytest.approx(1 / 62 + 1 / 61)
    assert selected[0].matched_by == ["keyword", "semantic"]


def test_exact_first_in_given_order_with_null_value() -> None:
    selected = fuse([(7, "exact"), (3, "alias")], [2, 7], [], META, 60, 10, 3)
    assert [s.rowid for s in selected][:2] == [7, 3]
    assert selected[0].matched_by == ["exact", "keyword"]
    assert selected[1].matched_by == ["alias"]
    assert selected[0].ranking_value is None


def test_dedup_within_source_but_not_across() -> None:
    selected = fuse([], [1, 5, 6], [], META, 60, 10, 3)
    assert [s.rowid for s in selected] == [1, 6]


def test_per_document_cap_and_limit() -> None:
    selected = fuse([], [1, 2, 3, 4, 7], [], META, 60, 10, 3)
    assert [s.rowid for s in selected] == [1, 2, 3, 7]
    assert len(fuse([], [1, 2, 3, 4, 7], [], META, 60, 2, 3)) == 2
    assert [s.rank for s in selected] == [1, 2, 3, 4]


def test_deterministic() -> None:
    args = ([], [4, 3, 2, 1], [1, 7, 6], META, 60, 10, 3)
    assert fuse(*args) == fuse(*args)
