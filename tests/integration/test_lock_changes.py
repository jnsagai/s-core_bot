"""Deleted and renamed source files between two locks (SC-007, US1 AS8). Mocked provider."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tests.helpers.build import build
from tests.helpers.snapshot_env import SourceSpec, default_sources, make_env


def _paths(data: Path, snapshot_id: str) -> set[tuple[str, str]]:
    corpus = data / "snapshots" / snapshot_id / "corpus.sqlite"
    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    return set(conn.execute("SELECT source_id, path FROM documents").fetchall())


def test_deleted_and_renamed_files(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    first = build(env)

    v2 = default_sources()
    alpha = v2[0]
    files = dict(alpha.files)
    del files["docs/sharealike.rst"]
    files["docs/renamed-guide.md"] = files.pop("docs/guide.md")
    v2[0] = SourceSpec("alpha", files, revision="c" * 40)
    env.write(v2)
    second = build(env)

    old = _paths(env.data, first.snapshot_id)
    new = _paths(env.data, second.snapshot_id)
    assert ("alpha", "docs/sharealike.rst") in old
    assert ("alpha", "docs/sharealike.rst") not in new
    assert ("alpha", "docs/guide.md") in old and ("alpha", "docs/guide.md") not in new
    assert ("alpha", "docs/renamed-guide.md") in new
    corpus = env.data / "snapshots" / first.snapshot_id / "corpus.sqlite"
    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    text = conn.execute("SELECT text FROM chunks WHERE path = 'docs/sharealike.rst'").fetchone()[0]
    assert "license review" in text
