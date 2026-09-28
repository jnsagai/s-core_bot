"""Snapshot and embedding manifests, file hashing, and the schema gate (FR-010, FR-017).

Readers check `schema_version` / `corpus_schema_version` on the raw JSON before validating any
other field, so a newer format is refused rather than partially read.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import (
    CORPUS_SCHEMA_VERSION,
    EMBEDDING_MANIFEST_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    EmbeddingManifest,
    FileEntry,
    SnapshotManifest,
)

MANIFEST_NAME = "manifest.json"
EMBEDDING_MANIFEST_NAME = "embedding-manifest.json"
VECTORS_NAME = "embeddings.f32"
CORPUS_NAME = "corpus.sqlite"
_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def list_files(directory: Path) -> list[str]:
    """Every regular file below `directory` except the manifest, as sorted POSIX paths."""
    found: list[str] = []
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        for name in files:
            relative = (Path(root) / name).relative_to(directory).as_posix()
            if relative != MANIFEST_NAME:
                found.append(relative)
    return sorted(found)


def hash_files(directory: Path) -> list[FileEntry]:
    return [
        FileEntry(path=p, sha256=sha256_file(directory / p), size=(directory / p).stat().st_size)
        for p in list_files(directory)
    ]


def dump_json(model: BaseModel) -> bytes:
    data = json.loads(model.model_dump_json())
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def write_json_file(path: Path, model: BaseModel) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(dump_json(model))
        handle.flush()
        os.fsync(handle.fileno())


def _load_raw(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError("CHECKSUM_MISMATCH", f"{path.name}: unreadable ({exc})") from exc
    if not isinstance(data, dict):
        raise SnapshotError("CHECKSUM_MISMATCH", f"{path.name}: not a JSON object")
    return data


def _gate(path: Path, data: dict[str, Any], field: str, supported: int) -> None:
    version = data.get(field)
    if not isinstance(version, int):
        raise SnapshotError("CHECKSUM_MISMATCH", f"{path.name}: missing {field}")
    if version > supported:
        raise SnapshotError(
            "SCHEMA_UNSUPPORTED",
            f"{path.name}: {field} {version} is newer than supported {supported}",
        )


def parse_snapshot_manifest(path: Path, data: dict[str, Any]) -> SnapshotManifest:
    _gate(path, data, "schema_version", SNAPSHOT_SCHEMA_VERSION)
    _gate(path, data, "corpus_schema_version", CORPUS_SCHEMA_VERSION)
    try:
        return SnapshotManifest.model_validate(data)
    except ValidationError as exc:
        raise SnapshotError("CHECKSUM_MISMATCH", f"{path.name}: invalid manifest ({exc})") from exc


def read_snapshot_manifest(directory: Path) -> SnapshotManifest:
    path = directory / MANIFEST_NAME
    return parse_snapshot_manifest(path, _load_raw(path))


def read_embedding_manifest(directory: Path) -> EmbeddingManifest:
    path = directory / EMBEDDING_MANIFEST_NAME
    data = _load_raw(path)
    _gate(path, data, "schema_version", EMBEDDING_MANIFEST_SCHEMA_VERSION)
    try:
        return EmbeddingManifest.model_validate(data)
    except ValidationError as exc:
        raise SnapshotError("CHECKSUM_MISMATCH", f"{path.name}: invalid ({exc})") from exc
