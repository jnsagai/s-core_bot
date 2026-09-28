"""Glob selectors (research.md R8): `**` whole segments, `*`/`?` never cross `/`."""

from __future__ import annotations

import pytest

from score_docs_assistant.sources.selectors import Selector, SelectorError, validate_glob


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("docs/**/*.rst", "docs/index.rst", True),
        ("docs/**/*.rst", "docs/a/b/c.rst", True),
        ("docs/**/*.rst", "docs/a/b/c.md", False),
        ("docs/**/*.rst", "other/docs/index.rst", False),
        ("docs/*.rst", "docs/index.rst", True),
        ("docs/*.rst", "docs/sub/index.rst", False),
        ("README.md", "README.md", True),
        ("README.md", "docs/README.md", False),
        ("**/*.md", "a.md", True),
        ("**/*.md", "x/y/a.md", True),
        ("docs/**", "docs/a", True),
        ("docs/**", "docs/a/b.rst", True),
        ("docs/**", "docs", False),
        ("doc?.rst", "docs.rst", True),
        ("doc?.rst", "doc/.rst", False),
        ("a.b", "aXb", False),
        ("*.rst", ".rst", True),
    ],
)
def test_matching(pattern: str, path: str, expected: bool) -> None:
    assert Selector(include=[pattern], exclude=[]).matches(path) is expected


def test_exclude_wins_over_include() -> None:
    selector = Selector(include=["docs/**/*.rst"], exclude=["docs/drafts/**"])
    assert selector.matches("docs/a.rst")
    assert not selector.matches("docs/drafts/a.rst")


def test_dot_git_always_excluded() -> None:
    selector = Selector(include=["**/*"], exclude=[])
    assert not selector.matches(".git/config")
    assert not selector.matches(".git/hooks/post-checkout")
    assert selector.matches(".github/workflow.yml")


@pytest.mark.parametrize(
    "pattern",
    ["docs/[ab].rst", "/docs/*.rst", "docs/../x", "docs//a", "docs/", "", "a\\b", "docs/a**b"],
)
def test_rejected_syntax(pattern: str) -> None:
    assert validate_glob(pattern) is not None
    with pytest.raises(SelectorError):
        Selector(include=[pattern], exclude=[])


def test_valid_syntax_has_no_error() -> None:
    assert validate_glob("docs/**/*.rst") is None
