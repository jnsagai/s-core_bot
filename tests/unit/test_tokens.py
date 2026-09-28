"""`pretoken-v1` conservative token estimate (FR-003, research R2)."""

from __future__ import annotations

import pytest

from score_docs_assistant.ingestion.tokens import TOKEN_COUNT_METHOD, estimate_tokens


def test_method_name() -> None:
    assert TOKEN_COUNT_METHOD == "pretoken-v1"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 2),
        ("hello", 3 + 2),  # ceil(5/2)
        ("ab cd", 1 + 1 + 2),
        ("feat_req__x", 2 + 1 + 2 + 1 + 1 + 1 + 2),  # feat|_|req|_|_|x
        ("2024", 4 + 2),
        ("a.b", 1 + 1 + 1 + 2),
        ("ä", 2 + 2),
        ("日本", 6 + 2),
    ],
)
def test_fixed_cases(text: str, expected: int) -> None:
    assert estimate_tokens(text) == expected


@pytest.mark.parametrize(
    ("a", "b"),
    [("hello world", "more text"), ("x" * 7, "y" * 9), ("ID_1.2", "[see] (a)")],
)
def test_subadditive_across_whitespace(a: str, b: str) -> None:
    assert estimate_tokens(a + " " + b) <= estimate_tokens(a) + estimate_tokens(b)


def test_deterministic() -> None:
    text = "The feature shall comply with ISO 26262-6 §7.4.2."
    assert estimate_tokens(text) == estimate_tokens(text)
