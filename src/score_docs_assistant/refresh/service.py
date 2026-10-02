"""`refresh`: upstream check → sync → build → gate → activate, as one operator-invoked run (F011).

Ordering and decisions (plan Key Design 1–4):

- A non-blocking flock on `data/locks/refresh.lock` refuses overlapping runs (`busy`); build and
  activation additionally take the existing single-writer ingest lock.
- "Up to date" needs every source unchanged upstream, an unchanged registry, and an active snapshot
  built from the current lock (manifest `lock_sha256`). Sync never rewrites an unchanged lock, so
  this comparison stays exact across polls.
- The build mirrors the active snapshot's mode and never downgrades semantic search.
- Only a candidate that passes the gate is activated, and only if the active snapshot is still the
  one the gate compared against.

`serve` never imports this module (FR-012).
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import ConfigError, SnapshotError
from score_docs_assistant.domain.ingestion import SourceLock
from score_docs_assistant.domain.snapshots import SnapshotManifest
from score_docs_assistant.models.runtime import EmbeddingProvider
from score_docs_assistant.refresh.gate import PromotionGate
from score_docs_assistant.refresh.models import (
    GateCheck,
    Outcome,
    RefreshRun,
    RefreshState,
    RevisionChange,
    SourceCheck,
)
from score_docs_assistant.refresh.state import read_state, write_state
from score_docs_assistant.refresh.upstream import UpstreamChecker, UpstreamCheckError
from score_docs_assistant.sources.git_client import GitClient
from score_docs_assistant.sources.lock import LOCK_FILENAME, read_lock
from score_docs_assistant.sources.registry import SourceRegistry
from score_docs_assistant.sources.sync import SyncService
from score_docs_assistant.storage.build import BuildService
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.lifecycle import activate_under_lock
from score_docs_assistant.storage.locks import IngestLock
from score_docs_assistant.storage.manifest import read_snapshot_manifest

Progress = Callable[[str], None]
ProviderFactory = Callable[[], EmbeddingProvider]
GateFactory = Callable[[AppConfig], PromotionGate]


@dataclass
class _Run:
    """Mutable record of one run, frozen into a `RefreshRun` at the end."""

    started_at: datetime
    active_before: str | None = None
    candidate: str | None = None
    candidate_semantic: str | None = None
    checks: list[SourceCheck] = field(default_factory=list)
    synced: bool = False
    lock_changed: bool = False
    revision_changes: list[RevisionChange] = field(default_factory=list)
    gate: list[GateCheck] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def timed(self, step: str) -> Iterator[None]:
        started = time.monotonic()
        try:
            yield
        finally:
            self.timings[step] = round(time.monotonic() - started, 3)


class _Finish(Exception):  # noqa: N818 — control flow, not an error
    def __init__(self, outcome: Outcome, reason: str, active_after: str | None = None) -> None:
        self.outcome = outcome
        self.reason = reason
        self.active_after = active_after
        super().__init__(reason)


class RefreshService:
    def __init__(
        self,
        config: AppConfig,
        registry: SourceRegistry,
        *,
        profiles_dir: Path,
        git: GitClient,
        provider_factory: ProviderFactory,
        gate_factory: GateFactory,
        http_client: httpx.Client | None = None,
        lexical_only: bool = False,
        now: Callable[[], datetime] | None = None,
        progress: Progress | None = None,
    ) -> None:
        self._config = config
        self._data = config.data_dir
        self._registry = registry
        self._profiles = profiles_dir
        self._git = git
        self._provider_factory = provider_factory
        self._gate_factory = gate_factory
        self._http = http_client
        self._lexical_only = lexical_only
        self._now = now or (lambda: datetime.now(UTC))
        self._progress = progress or (lambda _message: None)

    @property
    def lock_path(self) -> Path:
        return self._data / LOCK_FILENAME

    def run(self) -> RefreshRun:
        record = _Run(started_at=self._now())
        lock_fd = self._try_refresh_lock()
        if lock_fd is None:
            return self._result(record, "busy", "another refresh is running", None)
        try:
            state = self._state()
            try:
                self._steps(record, state)
                raise AssertionError("refresh steps always finish")  # pragma: no cover
            except _Finish as finish:
                run = self._result(record, finish.outcome, finish.reason, finish.active_after)
            except Exception as exc:
                # An unattended run must record why it stopped (e.g. a build crash on unexpected
                # upstream content); the active snapshot is untouched because activation is last.
                step = next(reversed(record.timings), "start")
                reason = f"unexpected error during {step}: {type(exc).__name__}: {exc}"
                run = self._result(record, "failed", reason, self._active()[0])
            if run.outcome != "busy":  # busy writes nothing (contracts/cli.md)
                self._save(state, run)
            return run
        finally:
            os.close(lock_fd)

    # --- steps -------------------------------------------------------------------------------

    def _steps(self, record: _Run, state: RefreshState) -> None:
        active_id, active = self._active()
        record.active_before = active_id
        lock_before = self._read_lock()

        with record.timed("check"):
            checker = UpstreamChecker(
                self._registry,
                git=self._git,
                http_client=self._http,
                check_exports=self._config.refresh.check_exports,
            )
            try:
                upstream = checker.check(lock_before, state.exports)
            except UpstreamCheckError as exc:
                raise _Finish("failed", f"upstream check failed: {exc}", active_id) from exc
        record.checks = upstream.checks
        for check in upstream.checks:
            self._progress(f"check {check.source_id}: {check.status} {check.detail}".rstrip())
        if upstream.all_unchanged and self._built_from_current_lock(active):
            raise _Finish("up-to-date", "no upstream change", active_id)

        with record.timed("sync"):
            sync = SyncService(
                self._registry,
                self._data,
                git=self._git,
                http_client=self._http,
                progress=self._progress,
                keep_unchanged_lock=True,
            ).run()
        record.synced = True
        if sync.exit_code != 0:
            failures = [f"{r.source_id}: {r.failure}" for r in sync.results if r.failure]
            raise _Finish("failed", "sync failed: " + "; ".join(failures), active_id)
        record.lock_changed = sync.lock_changed
        state.exports = {**state.exports, **upstream.validators}
        lock_after = self._read_lock()
        assert lock_after is not None
        record.revision_changes = _revision_changes(lock_before, lock_after)
        if self._built_from_current_lock(active):
            raise _Finish("up-to-date", "upstream content unchanged after sync", active_id)

        provider = self._build(record, active)
        assert record.candidate is not None

        with record.timed("gate"):
            record.gate = self._gate_factory(self._config).evaluate(
                record.candidate, active, lock_after
            )
        failed = [g.id for g in record.gate if g.status == "fail"]
        if failed:
            raise _Finish("held", f"gate failed: {', '.join(failed)}", active_id)

        with record.timed("activate"):
            self._activate(record, active_id, provider)
        raise _Finish("activated", f"activated {record.candidate}", record.candidate)

    def _build(self, record: _Run, active: SnapshotManifest | None) -> EmbeddingProvider | None:
        semantic = not self._lexical_only and (active is None or active.semantic == "present")
        provider: EmbeddingProvider | None = None
        with record.timed("build"):
            try:
                if semantic:
                    provider = self._provider_factory()
                result = BuildService(
                    config=self._config,
                    profiles_dir=self._profiles,
                    provider=provider,
                    lexical_only=not semantic,
                    progress=self._progress,
                ).run(self.lock_path)
            except SnapshotError as exc:
                if exc.code == "BUILD_BUSY":
                    raise _Finish("busy", exc.message, record.active_before) from exc
                raise _Finish(
                    "failed", f"build failed: {exc.code}: {exc.message}", record.active_before
                ) from exc
        record.candidate = result.snapshot_id
        record.candidate_semantic = result.semantic
        self._progress(f"build {result.snapshot_id} {result.state} semantic {result.semantic}")
        return provider

    def _activate(
        self, record: _Run, baseline: str | None, provider: EmbeddingProvider | None
    ) -> None:
        assert record.candidate is not None
        try:
            with IngestLock(self._data):
                catalog = Catalog.open(self._data, create=False)
                assert catalog is not None
                with catalog:
                    if catalog.active_id() != baseline:
                        raise _Finish(
                            "held",
                            "the active snapshot changed during refresh; candidate not activated",
                            catalog.active_id(),
                        )
                    activate_under_lock(
                        config=self._config,
                        catalog=catalog,
                        snapshot_id=record.candidate,
                        runtime=provider,
                        progress=self._progress,
                    )
        except SnapshotError as exc:
            if exc.code == "BUILD_BUSY":
                raise _Finish("busy", exc.message, baseline) from exc
            raise _Finish(
                "failed", f"activation failed: {exc.code}: {exc.message}", baseline
            ) from exc

    # --- helpers -----------------------------------------------------------------------------

    def _try_refresh_lock(self) -> int | None:
        path = self._data / "locks" / "refresh.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        return fd

    def _state(self) -> RefreshState:
        state = read_state(self._data)
        return state if isinstance(state, RefreshState) else RefreshState()

    def _read_lock(self) -> SourceLock | None:
        if not self.lock_path.is_file():
            return None
        try:
            return read_lock(self.lock_path)
        except ConfigError:
            return None

    def _active(self) -> tuple[str | None, SnapshotManifest | None]:
        catalog = Catalog.open(self._data, create=False)
        if catalog is None:
            return None, None
        with catalog:
            active_id = catalog.active_id()
        if active_id is None:
            return None, None
        try:
            return active_id, read_snapshot_manifest(self._data / "snapshots" / active_id)
        except SnapshotError:
            return active_id, None

    def _built_from_current_lock(self, active: SnapshotManifest | None) -> bool:
        if active is None or not self.lock_path.is_file():
            return False
        return hashlib.sha256(self.lock_path.read_bytes()).hexdigest() == active.lock_sha256

    def _result(
        self, record: _Run, outcome: Outcome, reason: str, active_after: str | None
    ) -> RefreshRun:
        return RefreshRun(
            started_at=record.started_at,
            finished_at=self._now(),
            outcome=outcome,
            reason=reason,
            active_before=record.active_before,
            active_after=active_after,
            candidate=record.candidate,
            candidate_semantic=record.candidate_semantic,  # type: ignore[arg-type]
            checks=record.checks,
            synced=record.synced,
            lock_changed=record.lock_changed,
            revision_changes=record.revision_changes,
            gate=record.gate,
            timings=record.timings,
        )

    def _save(self, state: RefreshState, run: RefreshRun) -> None:
        state.last_run = run
        if run.outcome in ("up-to-date", "activated"):
            state.last_success_at = run.finished_at
        write_state(self._data, state)


def _revision_changes(before: SourceLock | None, after: SourceLock) -> list[RevisionChange]:
    old = {s.source_id: s.revision for s in before.sources} if before else {}
    new = {s.source_id: s.revision for s in after.sources}
    return [
        RevisionChange(source_id=source_id, before=old.get(source_id), after=new.get(source_id))
        for source_id in sorted(set(old) | set(new))
        if old.get(source_id) != new.get(source_id)
    ]
