"""`SyncService(keep_unchanged_lock=True)`: polling adds no lock or archive files (F011 FR-004)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from score_docs_assistant.sources.git_client import GitClient
from score_docs_assistant.sources.lock import read_lock
from score_docs_assistant.sources.sync import SyncService
from tests.helpers.git_repos import git, make_plain_repo
from tests.helpers.registries import git_source, make_registry

FILE_GIT = GitClient(allowed_protocols=frozenset({"file"}))


def _service(data: Path, url: str, *, keep: bool, minutes: int) -> SyncService:
    moment = datetime(2026, 10, 2, tzinfo=UTC) + timedelta(minutes=minutes)
    return SyncService(
        make_registry([git_source("docs", url)]),
        data,
        git=FILE_GIT,
        now=lambda: moment,
        keep_unchanged_lock=keep,
    )


def _archive(data: Path) -> list[str]:
    return sorted(p.name for p in (data / "source-locks").iterdir())


def test_unchanged_sync_keeps_lock_and_archive(tmp_path: Path) -> None:
    repo = make_plain_repo(tmp_path / "repo")
    data = tmp_path / "data"
    first = _service(data, repo.url, keep=True, minutes=0).run()
    assert first.exit_code == 0 and first.lock_changed
    lock_bytes = (data / "source-lock.json").read_bytes()
    mtime = (data / "source-lock.json").stat().st_mtime_ns
    archive = _archive(data)

    second = _service(data, repo.url, keep=True, minutes=15).run()
    assert second.exit_code == 0 and not second.lock_changed
    assert (data / "source-lock.json").read_bytes() == lock_bytes
    assert (data / "source-lock.json").stat().st_mtime_ns == mtime
    assert _archive(data) == archive


def test_new_commit_rewrites_lock(tmp_path: Path) -> None:
    repo = make_plain_repo(tmp_path / "repo")
    data = tmp_path / "data"
    _service(data, repo.url, keep=True, minutes=0).run()
    (repo.path / "docs" / "new.rst").write_text("New\n===\n\nNew text.\n")
    git(repo.path, "add", "-A")
    git(repo.path, "commit", "-q", "-m", "change")
    head = git(repo.path, "rev-parse", "HEAD")

    outcome = _service(data, repo.url, keep=True, minutes=15).run()
    assert outcome.lock_changed
    assert read_lock(data / "source-lock.json").sources[0].revision == head
    assert len(_archive(data)) == 2


def test_default_behaviour_unchanged(tmp_path: Path) -> None:
    """`sources sync` (F002) still writes a fresh lock every run."""
    repo = make_plain_repo(tmp_path / "repo")
    data = tmp_path / "data"
    _service(data, repo.url, keep=False, minutes=0).run()
    outcome = _service(data, repo.url, keep=False, minutes=15).run()
    assert outcome.lock_changed
    assert read_lock(data / "source-lock.json").generated_at.minute == 15
