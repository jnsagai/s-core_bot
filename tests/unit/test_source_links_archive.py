"""Archived source locks give immutable links for older revisions (F007 research R7)."""

from __future__ import annotations

import json
from pathlib import Path

from score_docs_assistant.answers.citations import SourceLinks
from score_docs_assistant.sources.lock import LOCK_ARCHIVE_DIR, archive_lock
from tests.unit.test_citations import _item


def _write_lock(path: Path, revision: str, repo: str = "https://github.com/o/r.git") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "score-process",
                        "kind": "git",
                        "repository": repo,
                        "revision": revision,
                    }
                ]
            }
        )
    )
    return path


def test_archive_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    lock = _write_lock(tmp_path / "source-lock.json", "a" * 40)
    first = archive_lock(tmp_path, lock)
    second = archive_lock(tmp_path, lock)
    assert first == second and first.parent == tmp_path / LOCK_ARCHIVE_DIR
    assert first.read_bytes() == lock.read_bytes()
    _write_lock(lock, "b" * 40)
    assert archive_lock(tmp_path, lock) != first
    assert len(list((tmp_path / LOCK_ARCHIVE_DIR).glob("*.json"))) == 2


def test_links_cover_archived_and_current_revisions(tmp_path: Path) -> None:
    lock = _write_lock(tmp_path / "source-lock.json", "a" * 40)
    archive_lock(tmp_path, lock)
    _write_lock(lock, "b" * 40)
    links = SourceLinks.for_data_dir(tmp_path)
    old = links.url(_item("E1", revision="a" * 40))
    new = links.url(_item("E1", revision="b" * 40))
    assert old is not None and "/blob/" + "a" * 40 + "/" in old
    assert new is not None and "/blob/" + "b" * 40 + "/" in new
    assert links.url(_item("E1", revision="c" * 40)) is None  # exact revision only
    assert links.url(_item("E1", revision="a" * 40, revision_status="unverified")) is None


def test_unreadable_archive_entries_are_ignored(tmp_path: Path) -> None:
    (tmp_path / LOCK_ARCHIVE_DIR).mkdir()
    (tmp_path / LOCK_ARCHIVE_DIR / "broken.json").write_text("{not json")
    _write_lock(tmp_path / "source-lock.json", "a" * 40)
    assert SourceLinks.for_data_dir(tmp_path).url(_item("E1")) is not None


def test_no_locks_no_links(tmp_path: Path) -> None:
    assert SourceLinks.for_data_dir(tmp_path).url(_item("E1")) is None
