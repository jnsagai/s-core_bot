"""Keyword candidates: literal queries, filters inside ranking (FR-007, FR-008, research R2)."""

from __future__ import annotations

import sqlite3

import pytest

from score_docs_assistant.retrieval.lexical import keyword_candidates
from score_docs_assistant.retrieval.query import fts_expression
from score_docs_assistant.storage.corpus_db import open_corpus_readonly
from tests.helpers.search import SearchFixture, make_search_fixture


@pytest.fixture(scope="module")
def conn(tmp_path_factory: pytest.TempPathFactory) -> sqlite3.Connection:
    fx: SearchFixture = make_search_fixture(tmp_path_factory.mktemp("lexical"))
    return open_corpus_readonly(fx.data / "snapshots" / fx.snapshot_id / "corpus.sqlite")


def _rows(conn: sqlite3.Connection, query: str, **kw) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    expression, _ = fts_expression(query)
    ids = keyword_candidates(conn, expression, limit=kw.pop("limit", 30), **kw)
    return [
        conn.execute("SELECT source_id, kind FROM chunks WHERE rowid = ?", (i,)).fetchone()
        for i in ids
    ]


def test_filter_applies_before_ranking(conn: sqlite3.Connection) -> None:
    [(winner, _)] = _rows(conn, "watchdog", limit=1)
    loser = "beta" if winner == "alpha" else "alpha"
    filtered = _rows(conn, "watchdog", limit=1, sources=[loser])
    assert [s for s, _ in filtered] == [loser]  # would be absent if filtering happened after top-1


def test_kind_filter(conn: sqlite3.Connection) -> None:
    rows = _rows(conn, "bazel docs", kinds=["code"])
    assert rows and {k for _, k in rows} == {"code"}


@pytest.mark.parametrize("query", ['"', "AND", "NEAR(", "*", "-", "col:val", "... ???"])
def test_operator_only_queries_never_error(conn: sqlite3.Connection, query: str) -> None:
    _rows(conn, query)


def test_no_expression_no_candidates(conn: sqlite3.Connection) -> None:
    assert keyword_candidates(conn, None, limit=30) == []


def test_id_column_hit_ranks_first(conn: sqlite3.Connection) -> None:
    expression, _ = fts_expression("MLE.3.BP1")
    [first, *_] = keyword_candidates(conn, expression, limit=5)
    text = conn.execute("SELECT need_ids FROM chunks WHERE rowid = ?", (first,)).fetchone()[0]
    assert "MLE.3.BP1" in text
