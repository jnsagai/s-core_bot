"""`SourceAdapter` implementations (master spec §5.1; plan Structure Decision).

Each adapter acquires one registry source into `staging_root/<source_id>/<revision>/` and
describes it as a `LockedSource`. They own everything source-kind-specific (FR-003–FR-007,
FR-022); `SyncService` owns only orchestration (staging, required-source policy, placement, lock).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal

import httpx

from score_docs_assistant.domain.ingestion import LockedFile, LockedSource, SkippedEntry
from score_docs_assistant.ingestion.canonical import canonical_hash
from score_docs_assistant.sources.git_client import GitClient, TreeEntry
from score_docs_assistant.sources.http_fetch import fetch_export
from score_docs_assistant.sources.paths import UnsafePathError, ensure_within, safe_relative_path
from score_docs_assistant.sources.registry import ExportSource, GitSource, SyncLimits
from score_docs_assistant.sources.selectors import Selector

# Repository-root license/notice files acquired regardless of selectors (FR-022).
_NOTICE_FILE = re.compile(r"^(LICEN[CS]E|NOTICE|COPYING)([._-].*)?$", re.IGNORECASE)
_READ_ONLY = 0o444


class SourceFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class Budget:
    """Total bytes a whole sync may write (FR-007); shared by every adapter in one sync."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def spend(self, amount: int) -> None:
        self.used += amount
        if self.used > self.limit:
            raise SourceFailure("SYNC_CAP_EXCEEDED", f"total size exceeds {self.limit} bytes")


def write_read_only(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(_READ_ONLY)


class GitSourceAdapter:
    kind: ClassVar[Literal["git"]] = "git"

    def __init__(
        self,
        source: GitSource,
        *,
        git: GitClient,
        cache_dir: Path,
        limits: SyncLimits,
        budget: Budget,
        now: Callable[[], datetime],
        progress: Callable[[str], None],
    ) -> None:
        self.source = source
        self._git = git
        self._cache_dir = cache_dir
        self._limits = limits
        self._budget = budget
        self._now = now
        self._progress = progress

    def acquire(self, staging_root: Path) -> LockedSource:
        source = self.source
        sha = self._git.resolve_ref(source.repository, source.ref)
        self._progress(f"{source.source_id}: resolved {source.ref} -> {sha}")
        cache = self._cache_dir / f"{source.source_id}.git"
        commit = self._git.fetch_commit(source.repository, sha, cache)
        selector = Selector(source.include, source.exclude)

        wanted: list[tuple[TreeEntry, bool]] = []
        skipped: list[SkippedEntry] = []
        excluded = 0
        for entry in self._git.list_tree(cache, commit):
            is_notice = "/" not in entry.path and bool(_NOTICE_FILE.match(entry.path))
            if not (is_notice or selector.matches(entry.path)):
                excluded += 1
                continue
            if entry.mode == "120000":
                skipped.append(SkippedEntry(path=entry.path, reason="symlink"))
            elif entry.mode == "160000" or entry.type == "commit":
                skipped.append(SkippedEntry(path=entry.path, reason="submodule"))
            elif entry.type != "blob":
                skipped.append(SkippedEntry(path=entry.path, reason="unsafe_path"))
            elif entry.size is None or entry.size > self._limits.max_text_file_bytes:
                skipped.append(SkippedEntry(path=entry.path, reason="oversize"))
            else:
                try:
                    safe_relative_path(entry.path)
                except UnsafePathError:
                    skipped.append(SkippedEntry(path=entry.path, reason="unsafe_path"))
                    continue
                wanted.append((entry, is_notice))

        root = staging_root / source.source_id / commit
        root.mkdir(parents=True)
        blobs = dict(self._git.read_blobs(cache, sorted({e.oid for e, _ in wanted})))
        files: list[LockedFile] = []
        notices: list[LockedFile] = []
        for entry, is_notice in sorted(wanted, key=lambda item: item[0].path):
            data = blobs[entry.oid]
            self._budget.spend(len(data))
            write_read_only(ensure_within(root, safe_relative_path(entry.path)), data)
            locked = LockedFile(
                path=entry.path, sha256=hashlib.sha256(data).hexdigest(), size=len(data)
            )
            (notices if is_notice else files).append(locked)
        self._progress(f"{source.source_id}: extracted {len(files)} files, skipped {len(skipped)}")
        return LockedSource(
            source_id=source.source_id,
            kind="git",
            status="ok",
            required=source.required,
            repository=source.repository,
            ref=source.ref,
            authority=source.authority,
            repository_license=source.repository_license,
            parser_profile=source.parser_profile,
            revision=commit,
            revision_status="pinned",
            fetched_at=self._now(),
            selector_sha256=canonical_hash({"include": source.include, "exclude": source.exclude}),
            excluded_by_selector=excluded,
            files=files,
            notice_files=notices,
            skipped=sorted(skipped, key=lambda s: s.path),
        )


class ExportSourceAdapter:
    kind: ClassVar[Literal["needs-export"]] = "needs-export"

    def __init__(
        self,
        source: ExportSource,
        *,
        allowed_hosts: list[str],
        limits: SyncLimits,
        budget: Budget,
        http_client: httpx.Client | None,
        now: Callable[[], datetime],
        progress: Callable[[str], None],
    ) -> None:
        self.source = source
        self._allowed_hosts = allowed_hosts
        self._limits = limits
        self._budget = budget
        self._http = http_client
        self._now = now
        self._progress = progress

    def acquire(self, staging_root: Path) -> LockedSource:
        source = self.source
        fetched = fetch_export(
            source.url,
            allowed_hosts=self._allowed_hosts,
            max_bytes=self._limits.max_export_bytes,
            connect_timeout=self._limits.connect_timeout_seconds,
            read_timeout=self._limits.read_timeout_seconds,
            client=self._http,
        )
        self._budget.spend(fetched.size)
        write_read_only(
            staging_root / source.source_id / fetched.sha256 / "needs.json", fetched.data
        )
        self._progress(f"{source.source_id}: downloaded {fetched.size} bytes")
        return LockedSource(
            source_id=source.source_id,
            kind="needs-export",
            status="ok",
            required=source.required,
            url=source.url,
            associated_source=source.associated_source,
            docs_root=source.docs_root,
            authority=source.authority,
            repository_license=source.repository_license,
            revision=fetched.sha256,
            revision_status="unverified",
            fetched_at=self._now(),
            files=[LockedFile(path="needs.json", sha256=fetched.sha256, size=fetched.size)],
        )
