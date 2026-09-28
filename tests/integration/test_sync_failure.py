"""Failure safety: prior lock and revisions untouched, staging removed (FR-007, FR-008)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from score_docs_assistant.sources.git_client import GitClient
from score_docs_assistant.sources.lock import read_lock
from score_docs_assistant.sources.sync import SyncService
from tests.helpers.git_repos import make_plain_repo
from tests.helpers.registries import git_source, make_registry

FILE_GIT = GitClient(allowed_protocols=frozenset({"file"}))


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for dirpath, dirs, files in sorted(os.walk(root)):
        dirs.sort()
        for name in sorted(files):
            path = Path(dirpath) / name
            digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _run(data: Path, sources: list[dict[str, object]], **limits: int) -> int:
    registry = make_registry(sources, **limits)  # type: ignore[arg-type]
    return SyncService(registry, data, git=FILE_GIT).run().exit_code


@pytest.fixture
def synced(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = make_plain_repo(tmp_path / "good")
    data = tmp_path / "data"
    assert _run(data, [git_source("a-good", repo.url)]) == 0
    lock_bytes = (data / "source-lock.json").read_bytes()
    return data, repo.url, hashlib.sha256(lock_bytes).hexdigest(), _tree_digest(data / "sources")


def _staging_empty(data: Path) -> bool:
    staging = data / "staging"
    return not staging.exists() or list(staging.iterdir()) == []


def test_required_failure_keeps_previous_state(
    tmp_path: Path, synced: tuple[Path, str, str, str]
) -> None:
    data, good_url, lock_hash, tree = synced
    missing = (tmp_path / "does-not-exist").as_uri()
    code = _run(data, [git_source("a-good", good_url), git_source("b-bad", missing)])
    assert code == 1
    assert hashlib.sha256((data / "source-lock.json").read_bytes()).hexdigest() == lock_hash
    assert _tree_digest(data / "sources") == tree
    assert _staging_empty(data)


def test_optional_failure_is_recorded_not_fatal(
    tmp_path: Path, synced: tuple[Path, str, str, str]
) -> None:
    data, good_url, _, _ = synced
    missing = (tmp_path / "does-not-exist").as_uri()
    sources = [git_source("a-good", good_url), git_source("b-opt", missing, required=False)]
    assert _run(data, sources) == 0
    entries = {s.source_id: s for s in read_lock(data / "source-lock.json").sources}
    assert entries["a-good"].status == "ok"
    assert entries["b-opt"].status == "failed" and entries["b-opt"].failure
    assert _staging_empty(data)


def test_interrupt_cleans_staging_and_keeps_lock(
    monkeypatch: pytest.MonkeyPatch, synced: tuple[Path, str, str, str]
) -> None:
    data, good_url, lock_hash, _ = synced

    def interrupted(*args: object, **kwargs: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(GitClient, "fetch_commit", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _run(data, [git_source("a-good", good_url)])
    assert hashlib.sha256((data / "source-lock.json").read_bytes()).hexdigest() == lock_hash
    assert _staging_empty(data)


def test_total_size_cap_fails_required_source(
    tmp_path: Path, synced: tuple[Path, str, str, str]
) -> None:
    data, good_url, lock_hash, _ = synced
    assert _run(data, [git_source("a-good", good_url)], max_sync_bytes=60) == 1
    assert hashlib.sha256((data / "source-lock.json").read_bytes()).hexdigest() == lock_hash
    assert _staging_empty(data)
