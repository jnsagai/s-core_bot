"""Query handling: tokens, ID tokens, alias, safe FTS expressions, excerpts (R1, R2, R9)."""

from __future__ import annotations

import sqlite3

import pytest

from score_docs_assistant.retrieval.query import (
    MAX_QUERY_TERMS,
    alias,
    excerpt,
    fts_expression,
    id_tokens,
    tokenize,
)


def test_tokenize_whitespace() -> None:
    assert tokenize("  a  b\tc\nd ") == ["a", "b", "c", "d"]


def test_id_tokens_strip_trailing_sentence_punctuation() -> None:
    assert id_tokens("see feat_req__x. and (MLE.3.BP1), ok?") == [
        "see",
        "feat_req__x",
        "and",
        "MLE.3.BP1",
        "ok",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MLE.3.BP1", "mle_3_bp1"),
        ("mle-3-bp1", "mle_3_bp1"),
        ("FEAT_REQ__Baselibs__JSON", "feat_req_baselibs_json"),
        ("std_req__aspice_40__SWE-5-BP2", "std_req_aspice_40_swe_5_bp2"),
        ("--x--", "x"),
    ],
)
def test_alias(raw: str, expected: str) -> None:
    assert alias(raw) == expected


def test_fts_expression_quotes_everything() -> None:
    expression, truncated = fts_expression('say "hi" AND NEAR( x* -y col:val')
    assert expression == '"say" OR """hi""" OR "AND" OR "NEAR(" OR "x*" OR "-y" OR "col:val"'
    assert truncated is False


def test_fts_expression_drops_symbol_only_tokens_and_dedups() -> None:
    expression, _ = fts_expression("... ??? a a")
    assert expression == '"a"'
    assert fts_expression("... ---")[0] is None


def test_fts_expression_term_cap() -> None:
    query = " ".join(f"w{i}" for i in range(MAX_QUERY_TERMS + 10))
    expression, truncated = fts_expression(query)
    assert truncated is True
    assert expression is not None and expression.count(" OR ") == MAX_QUERY_TERMS - 1


@pytest.mark.parametrize(
    "query", ['"', "*", "AND", "NEAR(", "-", ":", "a OR", '"unbalanced', "(x", "x:y:z", "^a"]
)
def test_expressions_are_valid_fts5(query: str) -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize=\"unicode61 tokenchars '_-.'\")")
    conn.execute("INSERT INTO t VALUES ('a NEAR x*')")
    expression, _ = fts_expression(query)
    if expression is not None:
        conn.execute("SELECT count(*) FROM t WHERE t MATCH ?", (expression,)).fetchone()


def test_excerpt_cut_at_whitespace() -> None:
    text = "alpha beta gamma delta"
    assert excerpt(text, 100) == (text, False)
    cut, truncated = excerpt(text, 12)
    assert truncated is True and cut == "alpha beta"
    long_word, truncated = excerpt("x" * 50, 10)
    assert truncated and long_word == "x" * 10
