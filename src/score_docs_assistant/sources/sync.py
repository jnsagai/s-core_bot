"""`sources sync`: acquire every registry source into staging, then place revisions and write the
lock only if every required source succeeded (FR-003–FR-008, FR-022; plan Key Design 1–3).

Failure safety: nothing under `data/sources/` is modified before all sources are acquired; the
lock is replaced atomically and only on success; staging is removed on every exit path (including
Ctrl-C). If placement fails part-way, already-placed revision directories are complete and
immutable but unreferenced by any lock — harmless, and removed later by F003 retention.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from score_docs_assistant.domain.ingestion import (
    LockedFile,
    LockedSource,
    SkippedEntry,
    SourceLock,
)
from score_docs_assistant.ingestion.canonical import canonical_hash
from score_docs_assistant.sources.git_client import GitClient, GitError, TreeEntry
from score_docs_assistant.sources.http_fetch import FetchError, fetch_export
from score_docs_assistant.sources.lock import LOCK_FILENAME, source_root, verify_files, write_lock
from score_docs_assistant.sources.paths import UnsafePathError, ensure_within, safe_relative_path
from score_docs_assistant.sources.registry import ExportSource, GitSource, SourceRegistry
from score_docs_assistant.sources.selectors import Selector

# Repository-root license/notice files acquired regardless of selectors (FR-022).
_NOTICE_FILE = re.compile(r"^(LICEN[CS]E|NOTICE|COPYING)([._-].*)?$", re.IGNORECASE)
_READ_ONLY = 0o444


class _SourceFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class SourceResult:
    source_id: str
    status: str
    revision: str | None
    files: int
    skipped: int
    bytes: int
    failure: str | None


@dataclass
class SyncOutcome:
    exit_code: int
    lock_path: Path
    lock: SourceLock | None
    results: list[SourceResult] = field(default_factory=list)


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def spend(self, amount: int) -> None:
        self.used += amount
        if self.used > self.limit:
            raise _SourceFailure("SYNC_CAP_EXCEEDED", f"total size exceeds {self.limit} bytes")


def _write_read_only(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(_READ_ONLY)


class SyncService:
    def __init__(
        self,
        registry: SourceRegistry,
        data_dir: Path,
        *,
        git: GitClient | None = None,
        http_client: httpx.Client | None = None,
        now: Callable[[], datetime] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self._registry = registry
        self._data = data_dir
        limits = registry.limits
        self._git = git or GitClient(low_speed_seconds=limits.read_timeout_seconds)
        self._http = http_client
        self._now = now or (lambda: datetime.now(UTC))
        self._progress = progress or (lambda message: None)

    @property
    def lock_path(self) -> Path:
        return self._data / LOCK_FILENAME

    def run(self) -> SyncOutcome:
        staging = self._data / "staging" / f"sync-{uuid.uuid4().hex}"
        staging.mkdir(parents=True)
        try:
            return self._run(staging)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _run(self, staging: Path) -> SyncOutcome:
        budget = _Budget(self._registry.limits.max_sync_bytes)
        entries: list[LockedSource] = []
        staged: dict[str, Path] = {}
        results: list[SourceResult] = []
        required = {s.source_id: s.required for s in self._registry.sources}
        for source in sorted(self._registry.sources, key=lambda s: s.source_id):
            try:
                if isinstance(source, GitSource):
                    entry, path = self._acquire_git(source, staging, budget)
                else:
                    entry, path = self._acquire_export(source, staging, budget)
                staged[source.source_id] = path
            except (GitError, FetchError, _SourceFailure, UnsafePathError) as exc:
                code = getattr(exc, "code", "UNSAFE_PATH")
                entry = self._failed_entry(source, f"{code}: {exc}")
                self._progress(f"{source.source_id}: FAILED {code}: {exc}")
            entries.append(entry)
            results.append(self._result(entry))

        if any(e.status == "failed" and required[e.source_id] for e in entries):
            return SyncOutcome(1, self.lock_path, None, results)

        for entry in entries:
            if entry.status != "ok" or entry.revision is None:
                continue
            final = source_root(self._data, entry.source_id, entry.revision)
            if final.exists():
                if verify_files(final, entry):
                    self._progress(f"{entry.source_id}: existing revision differs from lock")
                    return SyncOutcome(1, self.lock_path, None, results)
                continue  # identical revision already present: reuse, never rewrite
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged[entry.source_id], final)

        lock = SourceLock(
            schema_version=1,
            generated_at=self._now(),
            registry_sha256=self._registry.sha256,
            redistribution_allowed_licenses=list(self._registry.redistribution_allowed_licenses),
            sources=entries,
        )
        write_lock(self.lock_path, lock)
        return SyncOutcome(0, self.lock_path, lock, results)

    @staticmethod
    def _result(entry: LockedSource) -> SourceResult:
        return SourceResult(
            source_id=entry.source_id,
            status=entry.status,
            revision=entry.revision,
            files=len(entry.files),
            skipped=len(entry.skipped),
            bytes=sum(f.size for f in [*entry.files, *entry.notice_files]),
            failure=entry.failure,
        )

    def _failed_entry(self, source: GitSource | ExportSource, failure: str) -> LockedSource:
        common = {
            "source_id": source.source_id,
            "status": "failed",
            "failure": failure,
            "required": source.required,
            "authority": source.authority,
            "repository_license": source.repository_license,
            "fetched_at": self._now(),
        }
        if isinstance(source, GitSource):
            return LockedSource(
                kind="git",
                repository=source.repository,
                ref=source.ref,
                parser_profile=source.parser_profile,
                revision_status="pinned",
                **common,  # type: ignore[arg-type]
            )
        return LockedSource(
            kind="needs-export",
            url=source.url,
            associated_source=source.associated_source,
            docs_root=source.docs_root,
            revision_status="unverified",
            **common,  # type: ignore[arg-type]
        )

    def _acquire_git(
        self, source: GitSource, staging: Path, budget: _Budget
    ) -> tuple[LockedSource, Path]:
        sha = self._git.resolve_ref(source.repository, source.ref)
        self._progress(f"{source.source_id}: resolved {source.ref} -> {sha}")
        cache = self._data / "cache" / "git" / f"{source.source_id}.git"
        commit = self._git.fetch_commit(source.repository, sha, cache)
        selector = Selector(source.include, source.exclude)
        max_file = self._registry.limits.max_text_file_bytes

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
            elif entry.size is None or entry.size > max_file:
                skipped.append(SkippedEntry(path=entry.path, reason="oversize"))
            else:
                try:
                    safe_relative_path(entry.path)
                except UnsafePathError:
                    skipped.append(SkippedEntry(path=entry.path, reason="unsafe_path"))
                    continue
                wanted.append((entry, is_notice))

        root = staging / source.source_id / commit
        root.mkdir(parents=True)
        blobs = dict(self._git.read_blobs(cache, sorted({e.oid for e, _ in wanted})))
        files: list[LockedFile] = []
        notices: list[LockedFile] = []
        for entry, is_notice in sorted(wanted, key=lambda item: item[0].path):
            data = blobs[entry.oid]
            budget.spend(len(data))
            _write_read_only(ensure_within(root, safe_relative_path(entry.path)), data)
            locked = LockedFile(
                path=entry.path, sha256=hashlib.sha256(data).hexdigest(), size=len(data)
            )
            (notices if is_notice else files).append(locked)
        self._progress(f"{source.source_id}: extracted {len(files)} files, skipped {len(skipped)}")
        return (
            LockedSource(
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
                selector_sha256=canonical_hash(
                    {"include": source.include, "exclude": source.exclude}
                ),
                excluded_by_selector=excluded,
                files=files,
                notice_files=notices,
                skipped=sorted(skipped, key=lambda s: s.path),
            ),
            root,
        )

    def _acquire_export(
        self, source: ExportSource, staging: Path, budget: _Budget
    ) -> tuple[LockedSource, Path]:
        limits = self._registry.limits
        fetched = fetch_export(
            source.url,
            allowed_hosts=self._registry.allowed_hosts,
            max_bytes=limits.max_export_bytes,
            connect_timeout=limits.connect_timeout_seconds,
            read_timeout=limits.read_timeout_seconds,
            client=self._http,
        )
        budget.spend(fetched.size)
        root = staging / source.source_id / fetched.sha256
        _write_read_only(root / "needs.json", fetched.data)
        self._progress(f"{source.source_id}: downloaded {fetched.size} bytes")
        return (
            LockedSource(
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
            ),
            root,
        )
