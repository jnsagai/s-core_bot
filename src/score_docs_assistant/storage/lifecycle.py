"""Activation, rollback and retention (FR-012–FR-015, research R7, R12).

Every operation runs under the single-writer ingest lock. Activation re-verifies the target's
checksums and schema, then switches state, pointer and history in one catalog transaction.
Retention always keeps the active snapshot and the current rollback target, never deletes a
pinned snapshot, and removes unreferenced source revisions afterwards.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import CorpusSnapshot
from score_docs_assistant.models.runtime import EmbeddingProvider
from score_docs_assistant.storage.build import chunker_config, remove_tree
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.locks import IngestLock
from score_docs_assistant.storage.manifest import (
    MANIFEST_NAME,
    list_files,
    read_snapshot_manifest,
    sha256_file,
)
from score_docs_assistant.storage.pins import ExclusiveHold
from score_docs_assistant.storage.validation import SnapshotValidator

Progress = Callable[[str], None]
_RETAINED_STATES = ("active", "validated", "retired")


def _snapshot_dir(config: AppConfig, snapshot_id: str) -> Path:
    return config.data_dir / "snapshots" / snapshot_id


def verify_for_activation(config: AppConfig, row: CorpusSnapshot) -> None:
    """Checksums and schema of every file, and the manifest hash registered in the catalog."""
    directory = _snapshot_dir(config, row.snapshot_id)
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise SnapshotError("CHECKSUM_MISMATCH", f"{row.snapshot_id}: {MANIFEST_NAME} missing")
    if row.manifest_sha256 != sha256_file(manifest_path):
        raise SnapshotError(
            "CHECKSUM_MISMATCH",
            f"{row.snapshot_id}: {MANIFEST_NAME} differs from the registered manifest",
        )
    manifest = read_snapshot_manifest(directory)
    listed = {f.path: f for f in manifest.files}
    present = set(list_files(directory))
    for path in sorted(present - set(listed)):
        raise SnapshotError("CHECKSUM_MISMATCH", f"{row.snapshot_id}: unlisted file {path}")
    for path, entry in sorted(listed.items()):
        target = directory / path
        if path not in present or sha256_file(target) != entry.sha256:
            raise SnapshotError(
                "CHECKSUM_MISMATCH", f"{row.snapshot_id}: {path} changed or missing"
            )


def activate_under_lock(
    *,
    config: AppConfig,
    catalog: Catalog,
    snapshot_id: str,
    runtime: EmbeddingProvider | None,
    progress: Progress,
    kind: str = "activate",
) -> list[str]:
    """Caller holds the ingest lock. Returns warnings (never raises for semantic problems)."""
    row = catalog.get(snapshot_id)
    if row is None:
        raise SnapshotError("SNAPSHOT_NOT_FOUND", f"no snapshot {snapshot_id}")
    if catalog.active_id() == snapshot_id:
        progress(f"{snapshot_id} is already active; nothing to do")
        return []
    if row.state not in ("validated", "retired"):
        raise SnapshotError("NOT_ACTIVATABLE", f"{snapshot_id} is {row.state}")
    verify_for_activation(config, row)

    warnings: list[str] = []
    manifest = read_snapshot_manifest(_snapshot_dir(config, snapshot_id))
    current = catalog.active_id()
    current_row = catalog.get(current) if current else None
    if manifest.semantic == "absent" and current_row and current_row.semantic == "present":
        warnings.append("semantic search will be unavailable (activating a lexical-only snapshot)")
    if manifest.semantic == "present":
        status, detail, guidance = SnapshotValidator(
            data_dir=config.data_dir,
            embedding_model=config.runtime.embedding_model,
            chunker_config=chunker_config(config),
            runtime=runtime,
        ).semantic_status(manifest)
        if status != "enabled":
            warnings.append(f"semantic {status}: {detail}" + "".join(f"; {g}" for g in guidance))

    previous = catalog.switch_active(snapshot_id, kind)
    progress(
        f"{'rolled back to' if kind == 'rollback' else 'activated'} {snapshot_id}"
        + (f" (previous: {previous})" if previous else "")
    )
    for message in run_retention(config=config, catalog=catalog):
        progress(message)
    return warnings


def activate(
    *, config: AppConfig, snapshot_id: str, runtime: EmbeddingProvider | None, progress: Progress
) -> list[str]:
    with IngestLock(config.data_dir):
        catalog = Catalog.open(config.data_dir, create=False)
        if catalog is None:
            raise SnapshotError("SNAPSHOT_NOT_FOUND", "no catalog yet; run `index build` first")
        with catalog:
            return activate_under_lock(
                config=config,
                catalog=catalog,
                snapshot_id=snapshot_id,
                runtime=runtime,
                progress=progress,
            )


def rollback(
    *, config: AppConfig, runtime: EmbeddingProvider | None, progress: Progress
) -> list[str]:
    with IngestLock(config.data_dir):
        catalog = Catalog.open(config.data_dir, create=False)
        if catalog is None:
            raise SnapshotError("NO_ROLLBACK_TARGET", "no catalog yet; nothing to roll back")
        with catalog:
            latest = catalog.latest_activation()
            target = latest.previous_id if latest else None
            if target is None:
                raise SnapshotError("NO_ROLLBACK_TARGET", "no previous snapshot to roll back to")
            row = catalog.get(target)
            if row is None or row.state != "retired" or not _snapshot_dir(config, target).is_dir():
                state = "missing" if row is None else row.state
                raise SnapshotError(
                    "NO_ROLLBACK_TARGET", f"previous snapshot {target} is {state}; cannot roll back"
                )
            return activate_under_lock(
                config=config,
                catalog=catalog,
                snapshot_id=target,
                runtime=runtime,
                progress=progress,
                kind="rollback",
            )


def run_retention(*, config: AppConfig, catalog: Catalog) -> list[str]:
    """Caller holds the ingest lock. Returns human-readable messages."""
    messages: list[str] = []
    rows = [s for s in catalog.snapshots() if s.state in _RETAINED_STATES]
    keep: list[str] = []
    active = catalog.active_id()
    latest = catalog.latest_activation()
    for must in (active, latest.previous_id if latest else None):
        if must is not None and must not in keep and any(r.snapshot_id == must for r in rows):
            keep.append(must)
    for row in rows:  # newest first
        if len(keep) >= config.index.retention_count:
            break
        if row.snapshot_id not in keep:
            keep.append(row.snapshot_id)
    retained: list[str] = list(keep)
    for row in rows:
        if row.snapshot_id in keep:
            continue
        hold = ExclusiveHold.try_acquire(config.data_dir, row.snapshot_id)
        if hold is None:
            messages.append(f"retention: kept {row.snapshot_id} (pinned by a reader)")
            retained.append(row.snapshot_id)
            continue
        try:
            remove_tree(_snapshot_dir(config, row.snapshot_id))
            catalog.mark_deleted(row.snapshot_id)
        finally:
            hold.release(remove_file=True)
        messages.append(f"retention: deleted {row.snapshot_id}")
    messages.extend(_prune_sources(config, retained))
    return messages


def _referenced_revisions(config: AppConfig, retained: list[str]) -> dict[str, set[str]] | None:
    referenced: dict[str, set[str]] = {}
    for snapshot_id in retained:
        try:
            manifest = read_snapshot_manifest(_snapshot_dir(config, snapshot_id))
        except SnapshotError:
            return None  # cannot know what it references; prune nothing
        for source_id, revision in manifest.source_revisions.items():
            referenced.setdefault(source_id, set()).add(revision)
    lock_path = config.data_dir / "source-lock.json"
    if lock_path.is_file():
        try:
            lock = json.loads(lock_path.read_text())
            for source in lock.get("sources", []):
                if source.get("revision"):
                    referenced.setdefault(source["source_id"], set()).add(source["revision"])
        except (OSError, ValueError):
            return None
    return referenced


def _prune_sources(config: AppConfig, retained: list[str]) -> list[str]:
    referenced = _referenced_revisions(config, retained)
    if referenced is None:
        return ["retention: source pruning skipped (a retained manifest or the lock is unreadable)"]
    messages: list[str] = []
    sources = config.data_dir / "sources"
    if sources.is_dir():
        for source_dir in sorted(p for p in sources.iterdir() if p.is_dir()):
            for revision_dir in sorted(p for p in source_dir.iterdir() if p.is_dir()):
                if revision_dir.name not in referenced.get(source_dir.name, set()):
                    shutil.rmtree(revision_dir)
                    messages.append(
                        f"retention: deleted source {source_dir.name}@{revision_dir.name}"
                    )
            if not any(source_dir.iterdir()):
                source_dir.rmdir()
    cache = config.data_dir / "cache" / "git"
    if cache.is_dir():
        for repo in sorted(cache.glob("*.git")):
            if repo.name.removesuffix(".git") not in referenced:
                shutil.rmtree(repo)
                messages.append(f"retention: deleted git cache {repo.name}")
    return messages
