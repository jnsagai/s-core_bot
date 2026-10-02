"""Cheap upstream change check for `refresh` (F011 FR-002, research R1).

Git sources: resolve the ref (`git ls-remote`) and compare with the lock; no objects are fetched.
Needs exports: conditional GET with the validators stored after the last successful sync; the body
is never read. Every request goes through the registry's allowlist, redirect rules and timeouts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from score_docs_assistant.domain.ingestion import SourceLock
from score_docs_assistant.refresh.models import ExportValidator, SourceCheck
from score_docs_assistant.sources.git_client import GitClient, GitError
from score_docs_assistant.sources.http_fetch import FetchError, probe_export
from score_docs_assistant.sources.registry import ExportSource, GitSource, SourceRegistry


class UpstreamCheckError(Exception):
    """A required source could not be checked; refresh ends `failed` without syncing."""


@dataclass
class UpstreamResult:
    checks: list[SourceCheck] = field(default_factory=list)
    registry_changed: bool = False
    # Validators seen now; the caller stores them only after a successful sync.
    validators: dict[str, ExportValidator] = field(default_factory=dict)

    @property
    def all_unchanged(self) -> bool:
        return not self.registry_changed and all(c.status == "unchanged" for c in self.checks)


class UpstreamChecker:
    def __init__(
        self,
        registry: SourceRegistry,
        *,
        git: GitClient,
        http_client: httpx.Client | None = None,
        check_exports: bool = True,
    ) -> None:
        self._registry = registry
        self._git = git
        self._http = http_client
        self._check_exports = check_exports

    def check(self, lock: SourceLock | None, stored: dict[str, ExportValidator]) -> UpstreamResult:
        locked = {s.source_id: s for s in lock.sources} if lock else {}
        result = UpstreamResult(
            registry_changed=lock is None or lock.registry_sha256 != self._registry.sha256
        )
        for source in sorted(self._registry.sources, key=lambda s: s.source_id):
            entry = locked.get(source.source_id)
            revision = entry.revision if entry and entry.status == "ok" else None
            if isinstance(source, GitSource):
                result.checks.append(self._check_git(source, revision))
            else:
                result.checks.append(
                    self._check_export(source, revision, stored.get(source.source_id), result)
                )
        return result

    def _check_git(self, source: GitSource, revision: str | None) -> SourceCheck:
        try:
            upstream = self._git.resolve_ref(source.repository, source.ref)
        except GitError as exc:
            if source.required:
                raise UpstreamCheckError(f"{source.source_id}: {exc.code}: {exc}") from exc
            return SourceCheck(
                source_id=source.source_id,
                kind="git",
                status="unknown",
                locked=revision,
                detail=f"{exc.code}: {exc}",
            )
        return SourceCheck(
            source_id=source.source_id,
            kind="git",
            status="unchanged" if upstream == revision else "changed",
            locked=revision,
            upstream=upstream,
            detail="" if revision else "not in the current lock",
        )

    def _check_export(
        self,
        source: ExportSource,
        revision: str | None,
        stored: ExportValidator | None,
        result: UpstreamResult,
    ) -> SourceCheck:
        def check(status: str, detail: str) -> SourceCheck:
            return SourceCheck(
                source_id=source.source_id,
                kind="needs-export",
                status=status,  # type: ignore[arg-type]
                locked=revision,
                detail=detail,
            )

        if not self._check_exports:
            return check("unknown", "export check disabled (refresh.check_exports: false)")
        usable = stored if stored is not None and stored.url == source.url else None
        limits = self._registry.limits
        try:
            probe = probe_export(
                source.url,
                etag=usable.etag if usable else None,
                last_modified=usable.last_modified if usable else None,
                allowed_hosts=self._registry.allowed_hosts,
                connect_timeout=limits.connect_timeout_seconds,
                read_timeout=limits.read_timeout_seconds,
                client=self._http,
            )
        except FetchError as exc:
            if source.required:
                raise UpstreamCheckError(f"{source.source_id}: {exc.code}: {exc}") from exc
            return check("unknown", f"{exc.code}: {exc}")
        if probe.etag or probe.last_modified:
            result.validators[source.source_id] = ExportValidator(
                url=source.url, etag=probe.etag, last_modified=probe.last_modified
            )
        if probe.status == "no_validator":
            return check("unknown", "server sends no ETag/Last-Modified")
        if usable is None:
            return check("unknown", "no stored validator")
        if revision is None:
            return check("changed", "not in the current lock")
        if probe.status == "not_modified":
            return check("unchanged", "304 not modified")
        return check("changed", "modified since the last sync")


def locked_revisions(lock: SourceLock | None) -> dict[str, str | None]:
    return {s.source_id: s.revision for s in lock.sources} if lock else {}
