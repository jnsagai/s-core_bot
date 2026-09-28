"""GitClient hardening and object-level access (FR-003, FR-005, SC-003; research R5)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from score_docs_assistant.sources.git_client import GitClient, GitError, GitNotFound
from tests.helpers.git_repos import make_branch_tag_repo, make_plain_repo, make_symlink_repo


def _file_client() -> GitClient:
    return GitClient(allowed_protocols=frozenset({"file"}))


def test_argv_and_env_hardening(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def spy(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setenv("GIT_DIR", "/tmp/hijack")
    monkeypatch.setenv("GIT_SSH_COMMAND", "touch /tmp/pwned")
    monkeypatch.setattr(subprocess, "run", spy)
    GitClient().run(["version"], cwd=tmp_path)
    call = calls[0]
    argv = call["argv"]
    assert argv[0] == "git"
    joined = " ".join(argv)
    for flag in (
        "protocol.allow=never",
        "protocol.https.allow=always",
        "core.hooksPath=/dev/null",
        "http.followRedirects=false",
        "transfer.fsckObjects=true",
        "submodule.recurse=false",
        "credential.helper=",
    ):
        assert flag in joined, flag
    assert "protocol.file.allow" not in joined
    env = call["env"]
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert env["GIT_ALLOW_PROTOCOL"] == "https"
    assert "GIT_DIR" not in env and "GIT_SSH_COMMAND" not in env
    assert call.get("shell", False) is False


@pytest.mark.parametrize(
    "url", ["file:///tmp/repo", "http://github.com/x.git", "ssh://github.com/x.git"]
)
def test_production_client_refuses_non_https(url: str) -> None:
    with pytest.raises(GitError) as exc_info:
        GitClient().resolve_ref(url, "main")
    assert exc_info.value.code == "PROTOCOL_NOT_ALLOWED"


def test_resolve_branch_and_tag(tmp_path: Path) -> None:
    repo = make_branch_tag_repo(tmp_path / "r")
    client = _file_client()
    assert client.resolve_ref(repo.url, "main") == repo.head
    dev = client.resolve_ref(repo.url, "dev")
    assert len(dev) == 40 and dev != repo.head
    assert client.resolve_ref(repo.url, "v1") == repo.head


def test_ambiguous_and_missing_refs(tmp_path: Path) -> None:
    repo = make_branch_tag_repo(tmp_path / "r")
    client = _file_client()
    with pytest.raises(GitError) as ambiguous:
        client.resolve_ref(repo.url, "dup")
    assert ambiguous.value.code == "REF_AMBIGUOUS"
    with pytest.raises(GitError) as missing:
        client.resolve_ref(repo.url, "nope")
    assert missing.value.code == "REF_NOT_FOUND"


def test_full_sha_skips_ls_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("ls-remote must not run for a full SHA")

    monkeypatch.setattr(subprocess, "run", forbidden)
    sha = "a" * 40
    assert GitClient().resolve_ref("https://github.com/x/y.git", sha) == sha


def test_fetch_list_and_read_exact_bytes(tmp_path: Path) -> None:
    repo = make_plain_repo(tmp_path / "r", {"a.rst": "Title\n", "docs/b.bin": b"\x00\x01\xff"})
    client = _file_client()
    cache = tmp_path / "cache.git"
    commit = client.fetch_commit(repo.url, repo.head, cache)
    assert commit == repo.head
    entries = {e.path: e for e in client.list_tree(cache, commit)}
    assert set(entries) == {"a.rst", "docs/b.bin"}
    assert entries["docs/b.bin"].mode == "100644" and entries["docs/b.bin"].size == 3
    blobs = dict(client.read_blobs(cache, [entries["a.rst"].oid, entries["docs/b.bin"].oid]))
    assert blobs[entries["a.rst"].oid] == b"Title\n"
    assert blobs[entries["docs/b.bin"].oid] == b"\x00\x01\xff"


def test_symlink_mode_reported(tmp_path: Path) -> None:
    repo = make_symlink_repo(tmp_path / "r")
    client = _file_client()
    cache = tmp_path / "cache.git"
    commit = client.fetch_commit(repo.url, repo.head, cache)
    modes = {e.path: e.mode for e in client.list_tree(cache, commit)}
    assert modes["docs/link.rst"] == "120000"


def test_missing_git_binary(tmp_path: Path) -> None:
    client = GitClient(git_binary=str(tmp_path / "no-such-git"))
    with pytest.raises(GitNotFound) as exc_info:
        client.resolve_ref("https://github.com/x/y.git", "main")
    assert exc_info.value.code == "GIT_NOT_FOUND"
    assert "git" in str(exc_info.value).lower()
