"""Path safety for acquired files (FR-006, SC-003)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from score_docs_assistant.sources.paths import UnsafePathError, ensure_within, safe_relative_path


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../outside.rst",
        "docs/../../outside.rst",
        "docs/./a.rst",
        "docs//a.rst",
        "",
        "docs/a.rst/",
        "docs\\a.rst",
        "docs/a\x00.rst",
        "a/" + "x" * 256 + ".rst",
        "..",
        ".",
    ],
)
def test_hostile_paths_rejected(path: str) -> None:
    with pytest.raises(UnsafePathError):
        safe_relative_path(path)


@pytest.mark.parametrize("path", ["README.md", "docs/a/b/index.rst", ".github/x.md", "a-b_c.1.rst"])
def test_normal_paths_accepted(path: str) -> None:
    assert safe_relative_path(path) == PurePosixPath(path)


def test_ensure_within_returns_path_inside_root(tmp_path: Path) -> None:
    target = ensure_within(tmp_path, safe_relative_path("docs/a.rst"))
    assert target == tmp_path / "docs" / "a.rst"


def test_symlinked_parent_directory_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        ensure_within(root, safe_relative_path("docs/a.rst"))


def test_symlinked_leaf_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.rst").symlink_to(tmp_path / "elsewhere.rst")
    with pytest.raises(UnsafePathError):
        ensure_within(root, safe_relative_path("a.rst"))
