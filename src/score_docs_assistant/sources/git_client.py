"""Hardened git access that never executes repository content (FR-003, FR-005; research R5).

Files are read from git *objects* (`ls-tree` + `cat-file --batch`) in a bare cache repository;
there is never a working-tree checkout, so hooks, attribute filters, LFS smudge and symlink
creation cannot happen. Every call uses a fixed argv (never a shell), a minimal environment (an
inherited `GIT_DIR`, `GIT_SSH_COMMAND` or `GIT_EXEC_PATH` could redirect or execute things), and
configuration that ignores the user's and system's gitconfig.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# Environment variables passed through: locale-independent operation, and proxy/CA settings a
# corporate network may need. Nothing here can make git run a program.
_PASSTHROUGH = (
    "PATH",
    "HOME",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)


class GitError(Exception):
    def __init__(self, code: str, message: str, returncode: int | None = None) -> None:
        self.code = code
        self.returncode = returncode
        super().__init__(message)


class GitNotFound(GitError):
    def __init__(self, binary: str) -> None:
        super().__init__(
            "GIT_NOT_FOUND",
            f"git executable {binary!r} not found; git >= 2.34 is required for `sources sync`",
        )


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    type: str
    oid: str
    size: int | None
    path: str


class GitClient:
    def __init__(
        self,
        *,
        allowed_protocols: frozenset[str] = frozenset({"https"}),
        git_binary: str = "git",
        timeout_seconds: float = 600,
        low_speed_seconds: int = 60,
    ) -> None:
        self._protocols = allowed_protocols
        self._binary = git_binary
        self._timeout = timeout_seconds
        self._low_speed_seconds = low_speed_seconds

    def _argv(self, args: list[str]) -> list[str]:
        config = [
            "protocol.allow=never",
            *(f"protocol.{p}.allow=always" for p in sorted(self._protocols)),
            "core.hooksPath=/dev/null",
            "core.symlinks=false",
            "core.fsmonitor=false",
            "http.followRedirects=false",
            "http.lowSpeedLimit=1000",
            f"http.lowSpeedTime={self._low_speed_seconds}",
            "transfer.fsckObjects=true",
            "fetch.fsckObjects=true",
            "submodule.recurse=false",
            "credential.helper=",
        ]
        argv = [self._binary]
        for item in config:
            argv += ["-c", item]
        return argv + args

    def _env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in _PASSTHROUGH if k in os.environ}
        env.update(
            {
                "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "",
                "SSH_ASKPASS": "",
                "GIT_LFS_SKIP_SMUDGE": "1",
                "GIT_ALLOW_PROTOCOL": ":".join(sorted(self._protocols)),
                "GIT_PROTOCOL_FROM_USER": "0",
            }
        )
        return env

    def run(self, args: list[str], *, cwd: Path, stdin: bytes | None = None) -> bytes:
        try:
            result = subprocess.run(
                self._argv(args),
                cwd=cwd,
                env=self._env(),
                input=stdin,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitNotFound(self._binary) from exc
        except subprocess.TimeoutExpired as exc:
            raise GitError("GIT_TIMEOUT", f"git {args[0]} timed out") from exc
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", "replace").strip()
            command = args[0] if args[0] != "--git-dir" else args[2]
            raise GitError(
                f"GIT_{command.upper().replace('-', '_')}_FAILED",
                f"git {command} failed: {stderr[:500]}",
                returncode=result.returncode,
            )
        return result.stdout

    def _check_url(self, url: str) -> None:
        if urlsplit(url).scheme not in self._protocols:
            raise GitError("PROTOCOL_NOT_ALLOWED", f"protocol of {url!r} is not allowed")

    def resolve_ref(self, url: str, ref: str) -> str:
        """Return the 40-hex SHA `ref` currently names (branch or tag, never both)."""
        if _FULL_SHA.match(ref):
            return ref
        self._check_url(url)
        heads, tags = f"refs/heads/{ref}", f"refs/tags/{ref}"
        try:
            out = self.run(["ls-remote", "--exit-code", url, heads, tags], cwd=Path("/"))
        except GitError as exc:
            # `ls-remote --exit-code` exits 2 when the repository answered but no ref matched.
            if exc.returncode == 2:
                raise GitError("REF_NOT_FOUND", f"ref {ref!r} not found in {url}") from exc
            raise
        found: dict[str, str] = {}
        for line in out.decode("utf-8").splitlines():
            sha, _, name = line.partition("\t")
            if name.endswith("^{}"):
                found[name[:-3]] = sha  # peeled annotated tag: the commit it points to
            else:
                found.setdefault(name, sha)
        matches = [found[n] for n in (heads, tags) if n in found]
        if not matches:
            raise GitError("REF_NOT_FOUND", f"ref {ref!r} not found in {url}")
        if len(matches) > 1:
            raise GitError("REF_AMBIGUOUS", f"{ref!r} names both a branch and a tag in {url}")
        return matches[0]

    def fetch_commit(self, url: str, sha: str, git_dir: Path) -> str:
        """Fetch exactly `sha` (depth 1) into a bare cache repository; return the commit SHA."""
        self._check_url(url)
        if not (git_dir / "HEAD").is_file():
            git_dir.mkdir(parents=True, exist_ok=True)
            self.run(["init", "--bare", "-q", str(git_dir)], cwd=git_dir.parent)
        self.run(
            [
                "--git-dir",
                str(git_dir),
                "fetch",
                "--depth",
                "1",
                "--no-tags",
                "--no-recurse-submodules",
                "--quiet",
                url,
                sha,
            ],
            cwd=git_dir,
        )
        commit = self.run(
            ["--git-dir", str(git_dir), "rev-parse", "--verify", f"{sha}^{{commit}}"], cwd=git_dir
        )
        return commit.decode("ascii").strip()

    def list_tree(self, git_dir: Path, commit: str) -> list[TreeEntry]:
        out = self.run(
            ["--git-dir", str(git_dir), "ls-tree", "-r", "-z", "-l", "--full-tree", commit],
            cwd=git_dir,
        )
        entries: list[TreeEntry] = []
        for record in out.split(b"\0"):
            if not record:
                continue
            meta, _, raw_path = record.partition(b"\t")
            mode, obj_type, oid, size = meta.decode("ascii").split()
            entries.append(
                TreeEntry(
                    mode=mode,
                    type=obj_type,
                    oid=oid,
                    size=None if size == "-" else int(size),
                    # Undecodable names are kept visibly (and later rejected as unsafe paths).
                    path=raw_path.decode("utf-8", "backslashreplace"),
                )
            )
        return entries

    def read_blobs(self, git_dir: Path, oids: list[str]) -> Iterator[tuple[str, bytes]]:
        if not oids:
            return
        stdin = "".join(f"{oid}\n" for oid in oids).encode("ascii")
        out = self.run(["--git-dir", str(git_dir), "cat-file", "--batch"], cwd=git_dir, stdin=stdin)
        pos = 0
        for _ in oids:
            header_end = out.index(b"\n", pos)
            oid, obj_type, size = out[pos:header_end].decode("ascii").split()
            if obj_type != "blob":
                raise GitError("NOT_A_BLOB", f"{oid} is a {obj_type}")
            start = header_end + 1
            end = start + int(size)
            yield oid, out[start:end]
            pos = end + 1  # trailing newline after each object
