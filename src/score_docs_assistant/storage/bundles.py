"""Snapshot bundles: export, inspect, import (FR-018–FR-020, research R10).

Contract: specs/003-snapshot-index/contracts/bundle.md. A bundle is untrusted input. Import checks
the whole archive (entry types, names, count, sizes, manifest, schema, free disk) in a first pass
that writes nothing. It extracts in a second pass with our own containment checks (never
`extractall`), verifies every hash, runs the full validator without a runtime (socket-free), and
only then registers the snapshot as `validated`. It is never activated.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from score_docs_assistant import __version__
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import (
    BUNDLE_FORMAT,
    CORPUS_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    BundleManifest,
    FileEntry,
    LicenseAcknowledgement,
)
from score_docs_assistant.sources.paths import UnsafePathError, ensure_within, safe_relative_path
from score_docs_assistant.storage.build import chunker_config, remove_tree
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.locks import IngestLock
from score_docs_assistant.storage.manifest import (
    MANIFEST_NAME,
    read_snapshot_manifest,
    sha256_file,
)
from score_docs_assistant.storage.pins import Pin
from score_docs_assistant.storage.validation import SnapshotValidator

BUNDLE_MANIFEST = "bundle-manifest.json"
PREFIX = "snapshot/"
MAX_MANIFEST_BYTES = 1024 * 1024
_CHUNK = 1024 * 1024
_EXPORTABLE = ("validated", "active", "retired")


def _reject(reason: str, detail: str) -> SnapshotError:
    return SnapshotError("BUNDLE_REJECTED", f"{reason}: {detail}")


@dataclass
class ExportResult:
    path: Path
    sha256: str
    manifest: BundleManifest


@dataclass
class InspectResult:
    manifest: BundleManifest
    snapshot_manifest: dict[str, object]


@dataclass
class ImportResult:
    snapshot_id: str
    already_present: bool


# --- export ------------------------------------------------------------------------------------


def export_bundle(
    *, config: AppConfig, snapshot_id: str, output: Path, acknowledgement: str | None
) -> ExportResult:
    if output.exists():
        raise _reject("output_exists", f"{output} already exists; choose another path")
    catalog = Catalog.open(config.data_dir, create=False)
    if catalog is None:
        raise SnapshotError("SNAPSHOT_NOT_FOUND", "no catalog yet; run `index build` first")
    with catalog:
        row = catalog.get(snapshot_id)
    if row is None or row.state not in _EXPORTABLE:
        state = "missing" if row is None else row.state
        raise SnapshotError("SNAPSHOT_NOT_FOUND", f"snapshot {snapshot_id} is {state}")
    directory = config.data_dir / "snapshots" / snapshot_id
    with Pin(config.data_dir, snapshot_id):
        manifest = read_snapshot_manifest(directory)
        if manifest.license_review and not acknowledgement:
            listed = ", ".join(f"{e.source_id}:{e.path}" for e in manifest.license_review)
            raise SnapshotError(
                "LICENSE_REVIEW_REQUIRED",
                f"documents require license review before redistribution: {listed}. Re-run "
                'with --acknowledge-license-review "<reason>" after reviewing them.',
            )
        entries = [
            FileEntry(
                path=PREFIX + MANIFEST_NAME,
                sha256=sha256_file(directory / MANIFEST_NAME),
                size=(directory / MANIFEST_NAME).stat().st_size,
            )
        ]
        for entry in manifest.files:
            actual = sha256_file(directory / entry.path)
            if actual != entry.sha256:
                raise SnapshotError(
                    "CHECKSUM_MISMATCH", f"{snapshot_id}: {entry.path} changed; not exported"
                )
            entries.append(FileEntry(path=PREFIX + entry.path, sha256=actual, size=entry.size))
        if row.manifest_sha256 != entries[0].sha256:
            raise SnapshotError("CHECKSUM_MISMATCH", f"{snapshot_id}: manifest changed")
        bundle = BundleManifest(
            bundle_format=BUNDLE_FORMAT,
            schema_version=manifest.schema_version,
            corpus_schema_version=manifest.corpus_schema_version,
            snapshot_id=snapshot_id,
            manifest_sha256=entries[0].sha256,
            created_at=datetime.now(UTC),
            app_version=__version__,
            files=entries,
            total_size=0,
            entry_count=len(entries) + 1,
            license_acknowledgement=(
                LicenseAcknowledgement(
                    reason=acknowledgement,
                    files=[f"{e.source_id}:{e.path}" for e in manifest.license_review],
                )
                if manifest.license_review and acknowledgement
                else None
            ),
        )
        # total_size includes the bundle manifest itself, whose size depends on total_size;
        # iterate until the serialized size is stable.
        size = 0
        for _ in range(5):
            candidate = bundle.model_copy(
                update={"total_size": sum(e.size for e in entries) + size}
            )
            encoded = _encode(candidate)
            if len(encoded) == size:
                break
            size = len(encoded)
        bundle = candidate
        mtime = int(manifest.created_at.timestamp())
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
        try:
            with tarfile.open(temporary, "w:gz", format=tarfile.PAX_FORMAT) as tar:
                _add_bytes(tar, BUNDLE_MANIFEST, _encode(bundle), mtime)
                for entry in entries:
                    source = directory / entry.path.removeprefix(PREFIX)
                    info = _info(entry.path, entry.size, mtime)
                    with source.open("rb") as handle:
                        tar.addfile(info, handle)
            os.replace(temporary, output)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    return ExportResult(path=output, sha256=sha256_file(output), manifest=bundle)


def _encode(bundle: BundleManifest) -> bytes:
    data = json.loads(bundle.model_dump_json())
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


def _info(name: str, size: int, mtime: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = mtime
    info.type = tarfile.REGTYPE
    return info


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes, mtime: int) -> None:
    tar.addfile(_info(name, len(data), mtime), io.BytesIO(data))


# --- pass 1: scan (inspect) --------------------------------------------------------------------


def _check_name(name: str) -> str:
    if name == BUNDLE_MANIFEST:
        return name
    if not name.startswith(PREFIX) or "\\" in name:
        raise _reject("unsafe_path", repr(name))
    try:
        safe_relative_path(name.removeprefix(PREFIX))
    except UnsafePathError as exc:
        raise _reject("unsafe_path", f"{name!r} ({exc})") from exc
    return name


def _parse_manifest(data: bytes) -> BundleManifest:
    try:
        raw = json.loads(data)
    except ValueError as exc:
        raise _reject("manifest_invalid", f"not JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise _reject("manifest_invalid", "not an object")
    if raw.get("bundle_format") != BUNDLE_FORMAT:
        raise _reject("manifest_invalid", f"unknown bundle_format {raw.get('bundle_format')!r}")
    for field, supported in (
        ("schema_version", SNAPSHOT_SCHEMA_VERSION),
        ("corpus_schema_version", CORPUS_SCHEMA_VERSION),
    ):
        value = raw.get(field)
        if not isinstance(value, int) or value > supported:
            raise _reject("schema_unsupported", f"{field} {value!r} > supported {supported}")
    try:
        return BundleManifest.model_validate(raw)
    except ValidationError as exc:
        raise _reject("manifest_invalid", str(exc)) from exc


def scan_bundle(
    *,
    config: AppConfig,
    path: Path,
    free_bytes: Callable[[Path], int] | None = None,
    check_disk: bool = True,
) -> BundleManifest:
    """Pass 1: headers only (streamed), nothing written. Raises BUNDLE_REJECTED."""
    caps = config.bundles
    manifest: BundleManifest | None = None
    sizes: dict[str, int] = {}
    total = 0
    try:
        with tarfile.open(path, mode="r|gz") as tar:
            for count, member in enumerate(tar, start=1):
                if count > caps.max_entries:
                    raise _reject("too_many_entries", f"more than {caps.max_entries} entries")
                if not member.isreg():
                    raise _reject("entry_type", f"{member.name!r} is not a regular file")
                name = _check_name(member.name)
                if name in sizes:
                    raise _reject("entry_mismatch", f"duplicate entry {name!r}")
                total += member.size
                if total > caps.max_total_bytes:
                    raise _reject("too_large", f"more than {caps.max_total_bytes} bytes")
                sizes[name] = member.size
                if count == 1:
                    if name != BUNDLE_MANIFEST or member.size > MAX_MANIFEST_BYTES:
                        raise _reject("manifest_invalid", f"first entry must be {BUNDLE_MANIFEST}")
                    handle = tar.extractfile(member)
                    assert handle is not None
                    manifest = _parse_manifest(handle.read(MAX_MANIFEST_BYTES + 1))
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise _reject("unreadable", str(exc)) from exc
    if manifest is None:
        raise _reject("manifest_invalid", "empty bundle")
    declared = {e.path: e.size for e in manifest.files}
    if set(sizes) != {BUNDLE_MANIFEST, *declared}:
        missing = sorted(set(declared) - set(sizes))
        extra = sorted(set(sizes) - set(declared) - {BUNDLE_MANIFEST})
        raise _reject("entry_mismatch", f"missing {missing}, unlisted {extra}")
    if any(sizes[p] != s for p, s in declared.items()):
        raise _reject("size_mismatch", "an entry's size differs from the bundle manifest")
    if total != manifest.total_size or len(sizes) != manifest.entry_count:
        raise _reject("size_mismatch", "total size or entry count differs from the manifest")
    if PREFIX + MANIFEST_NAME not in declared:
        raise _reject("entry_mismatch", f"missing {PREFIX + MANIFEST_NAME}")
    if check_disk:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        free = (free_bytes or (lambda p: shutil.disk_usage(p).free))(config.data_dir)
        required = manifest.total_size + caps.disk_margin_bytes
        if free < required:
            raise _reject("disk_insufficient", f"need {required} bytes free, have {free}")
    return manifest


def inspect_bundle(*, config: AppConfig, path: Path) -> InspectResult:
    manifest = scan_bundle(config=config, path=path, check_disk=False)
    snapshot_manifest: dict[str, object] = {}
    try:
        with tarfile.open(path, mode="r|gz") as tar:
            for member in tar:
                if member.name == PREFIX + MANIFEST_NAME:
                    handle = tar.extractfile(member)
                    assert handle is not None
                    data = handle.read(MAX_MANIFEST_BYTES * 16)
                    if hashlib.sha256(data).hexdigest() != manifest.manifest_sha256:
                        raise _reject("hash_mismatch", "snapshot manifest hash differs")
                    snapshot_manifest = json.loads(data)
                    break
    except (tarfile.TarError, OSError, ValueError) as exc:
        raise _reject("unreadable", str(exc)) from exc
    return InspectResult(manifest=manifest, snapshot_manifest=snapshot_manifest)


# --- pass 2: import ----------------------------------------------------------------------------


def _extract(path: Path, staging: Path, manifest: BundleManifest) -> None:
    expected = {e.path: e for e in manifest.files}
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        with tarfile.open(path, mode="r|gz") as tar:
            for member in tar:
                if member.name == BUNDLE_MANIFEST:
                    continue
                entry = expected.get(member.name)
                if entry is None or not member.isreg():
                    raise _reject("entry_mismatch", f"unexpected entry {member.name!r}")
                relative = safe_relative_path(member.name.removeprefix(PREFIX))
                target = ensure_within(staging, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                ensure_within(staging, relative)  # re-check after creating parents
                source = tar.extractfile(member)
                assert source is not None
                digest = hashlib.sha256()
                written = 0
                fd = os.open(target, flags, 0o644)
                with os.fdopen(fd, "wb") as out:
                    while block := source.read(_CHUNK):
                        written += len(block)
                        if written > member.size:
                            raise _reject("size_mismatch", f"{member.name} exceeds its header")
                        digest.update(block)
                        out.write(block)
                    out.flush()
                    os.fsync(out.fileno())
                if written != entry.size or digest.hexdigest() != entry.sha256:
                    raise _reject("hash_mismatch", f"{member.name} differs from the manifest")
    except (tarfile.TarError, OSError, EOFError, UnsafePathError) as exc:
        raise _reject("unreadable", str(exc)) from exc


def import_bundle(
    *, config: AppConfig, path: Path, free_bytes: Callable[[Path], int] | None = None
) -> ImportResult:
    manifest = scan_bundle(config=config, path=path, free_bytes=free_bytes)
    with IngestLock(config.data_dir):
        catalog = Catalog.open(config.data_dir, create=True)
        assert catalog is not None
        with catalog:
            existing = catalog.get(manifest.snapshot_id)
            if existing is not None and existing.state != "deleted":
                if existing.manifest_sha256 == manifest.manifest_sha256:
                    return ImportResult(manifest.snapshot_id, already_present=True)
                raise _reject(
                    "id_conflict",
                    f"{manifest.snapshot_id} already exists with a different manifest",
                )
            job_id = uuid.uuid4().hex
            staging = config.data_dir / "staging" / f"import-{job_id}"
            staging.mkdir(parents=True)
            catalog.start_job(job_id, "import", manifest.snapshot_id, os.getpid())
            try:
                _extract(path, staging, manifest)
                self_manifest = read_snapshot_manifest(staging)
                if sha256_file(staging / MANIFEST_NAME) != manifest.manifest_sha256:
                    raise _reject("hash_mismatch", "snapshot manifest differs")
                if self_manifest.snapshot_id != manifest.snapshot_id:
                    raise _reject("manifest_invalid", "snapshot ID differs between manifests")
                report = SnapshotValidator(
                    data_dir=config.data_dir,
                    embedding_model=config.runtime.embedding_model,
                    chunker_config=chunker_config(config),
                    runtime=None,
                ).validate(staging, expected_manifest_sha256=manifest.manifest_sha256)
                if not report.integrity_ok:
                    failed = [f"{c.id}: {c.detail}" for c in report.integrity if c.status == "fail"]
                    raise _reject("validation_failed", "; ".join(failed))
                for file in staging.rglob("*"):
                    if file.is_file():
                        file.chmod(0o444)
                snapshots = config.data_dir / "snapshots"
                snapshots.mkdir(parents=True, exist_ok=True)
                target = snapshots / manifest.snapshot_id
                if target.exists():
                    remove_tree(target)  # leftover of a deleted snapshot; row says deleted
                os.replace(staging, target)
                catalog.publish(
                    snapshot_id=manifest.snapshot_id,
                    job_id=job_id,
                    manifest_sha256=manifest.manifest_sha256,
                    schema_version=self_manifest.schema_version,
                    semantic=self_manifest.semantic,
                    chunks=self_manifest.counts.chunks,
                    created_at=self_manifest.created_at.isoformat().replace("+00:00", "Z"),
                )
            except BaseException as exc:
                remove_tree(staging)
                reason = exc.message if isinstance(exc, SnapshotError) else repr(exc)
                catalog.fail(job_id=job_id, snapshot_id=None, reason=reason)
                raise
    return ImportResult(manifest.snapshot_id, already_present=False)
