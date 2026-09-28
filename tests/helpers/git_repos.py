"""Builders for local fixture git repositories used instead of GitHub in tests (F002 T022).

Repositories are created with fixed author/committer identity and dates, so their commit SHAs are
deterministic. `GitClient(allowed_protocols={"file"})` fetches them over `file://`; production code
only ever allows `https`.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

_FIXED_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}

LICENSE_TEXT = "Apache License\nVersion 2.0, January 2004\n(fixture copy)\n"
NOTICE_TEXT = "Notices for the fixture project.\n"


@dataclass(frozen=True)
class FixtureRepo:
    path: Path
    url: str
    head: str


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env={**os.environ, **_FIXED_ENV},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init(root: Path) -> Path:
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    return root


def _write(repo: Path, files: dict[str, str | bytes]) -> None:
    for rel, content in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def _repo(path: Path) -> FixtureRepo:
    return FixtureRepo(path=path, url=path.resolve().as_uri(), head=git(path, "rev-parse", "HEAD"))


def default_files() -> dict[str, str | bytes]:
    return {
        "LICENSE": LICENSE_TEXT,
        "NOTICE": NOTICE_TEXT,
        "README.md": "# Fixture\n\nSYNTHETIC — not S-CORE guidance.\n",
        "docs/index.rst": "Index\n=====\n\nSYNTHETIC — not S-CORE guidance.\n",
        "docs/guide/setup.rst": "Setup\n=====\n\nRun the build.\n",
        "docs/notes.md": "# Notes\n\nText.\n",
        "src/main.py": "print('not selected')\n",
    }


def make_plain_repo(root: Path, files: dict[str, str | bytes] | None = None) -> FixtureRepo:
    repo = _init(root)
    _write(repo, files if files is not None else default_files())
    _commit(repo, "fixture")
    return _repo(repo)


def make_repo_from_tree(root: Path, tree: Path) -> FixtureRepo:
    """Commit a copy of an existing directory tree (e.g. tests/fixtures/upstream/score)."""
    repo = _init(root)
    for item in tree.iterdir():
        dest = repo / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    _commit(repo, "fixture from tree")
    return _repo(repo)


def make_symlink_repo(root: Path) -> FixtureRepo:
    repo = _init(root)
    _write(repo, {**default_files(), "outside.rst": "Outside\n=======\n"})
    os.symlink("../outside.rst", repo / "docs" / "link.rst")
    os.symlink("/etc", repo / "docs" / "etc")
    _commit(repo, "symlinks")
    return _repo(repo)


def make_submodule_repo(root: Path) -> FixtureRepo:
    repo = _init(root)
    _write(repo, default_files())
    git(repo, "add", "-A")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{'a' * 40},docs/sub")
    git(repo, "commit", "-q", "-m", "gitlink")
    return _repo(repo)


def _executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_hooks_filters_repo(root: Path, marker: Path) -> FixtureRepo:
    """Content that would run code on checkout: hook scripts, attribute filters, LFS pointer."""
    repo = _init(root)
    files = default_files()
    files[".gitattributes"] = "*.rst filter=evil\n*.bin filter=lfs diff=lfs merge=lfs -text\n"
    files["docs/big.bin"] = (
        f"version https://git-lfs.github.com/spec/v1\noid sha256:{'0' * 64}\nsize 12345\n"
    )
    _write(repo, files)
    _executable(repo / ".githooks" / "post-checkout", f"#!/bin/sh\ntouch {marker}\n")
    _commit(repo, "hooks and filters")
    # Repo-local config is not transferred by fetch, but set it anyway to mirror a hostile clone.
    git(repo, "config", "core.hooksPath", ".githooks")
    git(repo, "config", "filter.evil.smudge", f"touch {marker}; cat")
    return _repo(repo)


def make_malicious_global_config(root: Path, marker: Path) -> Path:
    """A user-level gitconfig whose hooks/filters would create `marker` if git honoured it."""
    hooks = root / "global-hooks"
    for name in ("reference-transaction", "post-checkout", "post-merge", "pre-auto-gc"):
        _executable(hooks / name, f"#!/bin/sh\ntouch {marker}\n")
    config = root / "gitconfig"
    config.write_text(
        f"[core]\n\thooksPath = {hooks}\n"
        f'[filter "evil"]\n\tsmudge = touch {marker}; cat\n'
        '[url "file:///nonexistent/"]\n\tinsteadOf = https://\n'
    )
    return config


def make_oversize_repo(root: Path, size: int) -> FixtureRepo:
    files = default_files()
    files["docs/huge.rst"] = "A" * size
    return make_plain_repo(root, files)


def make_branch_tag_repo(root: Path) -> FixtureRepo:
    """`main`, branch `dev`, tag `v1`, and the name `dup` as both a branch and a tag."""
    repo = _init(root)
    _write(repo, default_files())
    _commit(repo, "first")
    git(repo, "tag", "v1")
    git(repo, "branch", "dup")
    git(repo, "tag", "dup")
    git(repo, "checkout", "-q", "-b", "dev")
    _write(repo, {"docs/dev.rst": "Dev\n===\n"})
    _commit(repo, "dev")
    git(repo, "checkout", "-q", "main")
    return _repo(repo)
