"""Includes resolve only inside the pinned, selected file set (FR-015, SC-003)."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.ingestion.rst.parser import IncludeContext
from tests.helpers.parsing import codes, parse_rst, walk


@pytest.fixture
def tree(tmp_path: Path) -> IncludeContext:
    root = tmp_path / "rev"
    files = {
        "docs/main.rst": "",
        "docs/part.rst": "Included paragraph\non two lines.\n",
        "docs/snippet.py": "print('x')\n",
        "docs/cycle_a.rst": ".. include:: cycle_b.rst\n",
        "docs/cycle_b.rst": ".. include:: cycle_a.rst\n",
        "docs/unselected.rst": "Should not appear.\n",
    }
    for depth in range(10):
        files[f"docs/deep{depth}.rst"] = f".. include:: deep{depth + 1}.rst\n"
    files["docs/deep10.rst"] = "Bottom.\n"
    for rel, content in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content)
    (tmp_path / "outside.rst").write_text("Outside the root.\n")
    selected = {p for p in files if p != "docs/unselected.rst"}
    return IncludeContext(root=root, selected=selected)


def test_valid_include_keeps_origin_and_lines(tree: IncludeContext) -> None:
    result = parse_rst(
        "Main\n====\n\n.. include:: part.rst\n", path="docs/main.rst", include_context=tree
    )
    para = next(b for b in walk(result.blocks) if "Included paragraph" in b.text)
    assert para.origin_path == "docs/part.rst"
    assert (para.line_start, para.line_end) == (1, 2)
    assert "INCLUDE_UNRESOLVED" not in codes(result)


@pytest.mark.parametrize(
    "directive",
    [
        ".. include:: ../../outside.rst",
        ".. include:: /etc/passwd",
        ".. include:: missing.rst",
        ".. include:: unselected.rst",
        ".. include:: <isonum.txt>",
        ".. include:: part.rst\n   :url: https://example.invalid/x.rst",
    ],
)
def test_refused_includes(tree: IncludeContext, directive: str) -> None:
    result = parse_rst(directive + "\n", path="docs/main.rst", include_context=tree)
    assert "INCLUDE_UNRESOLVED" in codes(result)
    text = " ".join(b.text for b in walk(result.blocks))
    assert "Outside the root" not in text and "Should not appear" not in text
    assert "root:" not in text  # /etc/passwd content


def test_cycle_detected(tree: IncludeContext) -> None:
    result = parse_rst(".. include:: cycle_a.rst\n", path="docs/main.rst", include_context=tree)
    assert "INCLUDE_UNRESOLVED" in codes(result)


def test_depth_limit(tree: IncludeContext) -> None:
    result = parse_rst(".. include:: deep0.rst\n", path="docs/main.rst", include_context=tree)
    assert "INCLUDE_UNRESOLVED" in codes(result)
    assert "Bottom." not in " ".join(b.text for b in walk(result.blocks))


def test_no_context_means_no_include(tree: IncludeContext) -> None:
    result = parse_rst(".. include:: part.rst\n", path="docs/main.rst")
    assert "INCLUDE_UNRESOLVED" in codes(result)


def test_literalinclude_is_literal(tree: IncludeContext) -> None:
    result = parse_rst(
        ".. literalinclude:: snippet.py\n   :language: python\n",
        path="docs/main.rst",
        include_context=tree,
    )
    (code,) = [b for b in walk(result.blocks) if b.kind == "code"]
    assert code.text == "print('x')" and code.attrs["language"] == "python"
    assert code.origin_path == "docs/snippet.py"
