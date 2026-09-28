"""`sources sync`: acquire every registry source into staging, then place revisions and write the
lock only if every required source succeeded (FR-003–FR-008, FR-022; plan Key Design 1–3).

Failure safety: nothing under `data/sources/` is modified before all sources are acquired; the
lock is replaced atomically and only on success; staging is removed on every exit path (including
Ctrl-C). If placement fails part-way, already-placed revision directories are complete and
immutable but unreferenced by any lock — harmless, and removed later by F003 retention.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from score_docs_assistant.domain.ingestion import LockedSource, SourceAdapter, SourceLock
from score_docs_assistant.sources.adapters import (
    Budget,
    ExportSourceAdapter,
    GitSourceAdapter,
    SourceFailure,
)
from score_docs_assistant.sources.git_client import GitClient, GitError
from score_docs_assistant.sources.http_fetch import FetchError
from score_docs_assistant.sources.lock import LOCK_FILENAME, source_root, verify_files, write_lock
from score_docs_assistant.sources.paths import UnsafePathError
from score_docs_assistant.sources.registry import ExportSource, GitSource, SourceRegistry


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
        budget = Budget(self._registry.limits.max_sync_bytes)
        entries: list[LockedSource] = []
        staged: dict[str, Path] = {}
        results: list[SourceResult] = []
        required = {s.source_id: s.required for s in self._registry.sources}
        for source in sorted(self._registry.sources, key=lambda s: s.source_id):
            adapter = self._adapter(source, budget)
            try:
                entry = adapter.acquire(staging)
                staged[source.source_id] = staging / source.source_id / (entry.revision or "")
            except (GitError, FetchError, SourceFailure, UnsafePathError) as exc:
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

    def _adapter(self, source: GitSource | ExportSource, budget: Budget) -> SourceAdapter:
        limits = self._registry.limits
        if isinstance(source, GitSource):
            return GitSourceAdapter(
                source,
                git=self._git,
                cache_dir=self._data / "cache" / "git",
                limits=limits,
                budget=budget,
                now=self._now,
                progress=self._progress,
            )
        return ExportSourceAdapter(
            source,
            allowed_hosts=self._registry.allowed_hosts,
            limits=limits,
            budget=budget,
            http_client=self._http,
            now=self._now,
            progress=self._progress,
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
