"""`SyncService` against fixture git repositories (FR-003–FR-007, FR-022, SC-003)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from score_docs_assistant.domain.ingestion import LockedSource
from score_docs_assistant.sources.git_client import GitClient
from score_docs_assistant.sources.lock import read_lock
from score_docs_assistant.sources.sync import SyncService
from tests.helpers.git_repos import (
    default_files,
    make_hooks_filters_repo,
    make_malicious_global_config,
    make_oversize_repo,
    make_plain_repo,
    make_submodule_repo,
    make_symlink_repo,
)
from tests.helpers.registries import git_source, make_registry

FILE_GIT = GitClient(allowed_protocols=frozenset({"file"}))


def _sync(data_dir: Path, sources: list[dict[str, object]], **limits: int) -> int:
    registry = make_registry(sources, **limits)  # type: ignore[arg-type]
    return SyncService(registry, data_dir, git=FILE_GIT).run().exit_code


def _only(data_dir: Path) -> LockedSource:
    lock = read_lock(data_dir / "source-lock.json")
    assert len(lock.sources) == 1
    return lock.sources[0]


def _all_paths(root: Path) -> list[Path]:
    return [Path(dirpath) / name for dirpath, dirs, files in os.walk(root) for name in dirs + files]


def test_lock_fields_and_acquired_bytes(tmp_path: Path) -> None:
    repo = make_plain_repo(tmp_path / "repo")
    data = tmp_path / "data"
    assert _sync(data, [git_source("docs", repo.url)]) == 0
    entry = _only(data)
    assert entry.status == "ok" and entry.revision == repo.head and entry.ref == "main"
    assert entry.revision_status == "pinned" and entry.release_mapping is None
    assert entry.fetched_at.tzinfo is not None
    assert entry.selector_sha256 is not None and len(entry.selector_sha256) == 64
    assert entry.parser_profile == "s-core" and entry.repository_license == "Apache-2.0"
    selected = ["README.md", "docs/guide/setup.rst", "docs/index.rst", "docs/notes.md"]
    assert [f.path for f in entry.files] == selected
    assert entry.excluded_by_selector == 1  # src/main.py (LICENSE/NOTICE are notice files)
    root = data / "sources" / "docs" / repo.head
    source_files = default_files()
    for locked in entry.files:
        on_disk = root / locked.path
        assert on_disk.read_bytes() == str(source_files[locked.path]).encode()
        assert stat.S_IMODE(on_disk.stat().st_mode) == 0o444
        assert locked.size == on_disk.stat().st_size


def test_notice_files_acquired_despite_selectors(tmp_path: Path) -> None:
    repo = make_plain_repo(tmp_path / "repo")
    data = tmp_path / "data"
    _sync(data, [git_source("docs", repo.url, include=["docs/**/*.rst"])])
    entry = _only(data)
    assert [f.path for f in entry.notice_files] == ["LICENSE", "NOTICE"]
    assert (data / "sources" / "docs" / repo.head / "LICENSE").is_file()


def test_symlinks_and_submodules_skipped_nothing_outside_root(tmp_path: Path) -> None:
    sym = make_symlink_repo(tmp_path / "sym")
    sub = make_submodule_repo(tmp_path / "sub")
    data = tmp_path / "data"
    include = ["docs/**"]
    assert _sync(data, [git_source("sym", sym.url, include=include)]) == 0
    reasons = {s.path: s.reason for s in _only(data).skipped}
    assert reasons == {"docs/link.rst": "symlink", "docs/etc": "symlink"}
    (data / "source-lock.json").unlink()
    assert _sync(data, [git_source("sub", sub.url, include=include)]) == 0
    assert {s.path: s.reason for s in _only(data).skipped} == {"docs/sub": "submodule"}
    for path in _all_paths(data / "sources"):
        assert not path.is_symlink(), path
        assert path.resolve().is_relative_to((data / "sources").resolve())


def test_oversize_file_skipped_not_truncated(tmp_path: Path) -> None:
    repo = make_oversize_repo(tmp_path / "repo", size=5000)
    data = tmp_path / "data"
    assert _sync(data, [git_source("docs", repo.url)], max_text_file_bytes=4000) == 0
    entry = _only(data)
    assert {s.path: s.reason for s in entry.skipped} == {"docs/huge.rst": "oversize"}
    assert not (data / "sources" / "docs" / repo.head / "docs" / "huge.rst").exists()


def test_hooks_filters_lfs_and_global_config_never_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "EXECUTED"
    repo = make_hooks_filters_repo(tmp_path / "repo", marker)
    evil_config = make_malicious_global_config(tmp_path / "evil", marker)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(evil_config))
    monkeypatch.setenv("HOME", str(tmp_path / "evil"))
    data = tmp_path / "data"
    include = ["docs/**", ".gitattributes", ".githooks/**"]
    assert _sync(data, [git_source("docs", repo.url, include=include)]) == 0
    assert not marker.exists()
    root = data / "sources" / "docs" / repo.head
    assert (root / "docs" / "big.bin").read_text().startswith("version https://git-lfs")
    assert (root / "docs" / "index.rst").read_text() == default_files()["docs/index.rst"]
    hook = root / ".githooks" / "post-checkout"
    assert hook.is_file() and not os.access(hook, os.X_OK)


def test_resync_same_commit_reuses_revision_directory(tmp_path: Path) -> None:
    repo = make_plain_repo(tmp_path / "repo")
    data = tmp_path / "data"
    _sync(data, [git_source("docs", repo.url)])
    target = data / "sources" / "docs" / repo.head / "docs" / "index.rst"
    before = target.stat()
    assert _sync(data, [git_source("docs", repo.url)]) == 0
    after = target.stat()
    assert (before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)
    assert list((data / "staging").iterdir()) == []
