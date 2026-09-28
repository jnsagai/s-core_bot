"""Manifest helpers and schema gate (FR-010, FR-017). Full-manifest content is covered by the
build integration tests; here: hashing, listing, schema refusal before other fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.manifest import (
    hash_files,
    list_files,
    read_embedding_manifest,
    read_snapshot_manifest,
    sha256_file,
)


def test_list_and_hash_exclude_manifest(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "b.json").write_text("b")
    (tmp_path / "a.bin").write_bytes(b"a")
    (tmp_path / "manifest.json").write_text("{}")
    assert list_files(tmp_path) == ["a.bin", "reports/b.json"]
    entries = hash_files(tmp_path)
    assert [e.path for e in entries] == ["a.bin", "reports/b.json"]
    assert entries[0].sha256 == sha256_file(tmp_path / "a.bin")
    assert entries[0].size == 1


@pytest.mark.parametrize(
    ("data", "code"),
    [
        ({"schema_version": 2, "corpus_schema_version": 1, "garbage": True}, "SCHEMA_UNSUPPORTED"),
        ({"schema_version": 1, "corpus_schema_version": 9}, "SCHEMA_UNSUPPORTED"),
        ({"corpus_schema_version": 1}, "CHECKSUM_MISMATCH"),
        ({"schema_version": 1, "corpus_schema_version": 1}, "CHECKSUM_MISMATCH"),
    ],
)
def test_snapshot_manifest_gate(tmp_path: Path, data: dict[str, object], code: str) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps(data))
    with pytest.raises(SnapshotError) as exc_info:
        read_snapshot_manifest(tmp_path)
    assert exc_info.value.code == code


def test_unreadable_manifest(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("not json")
    with pytest.raises(SnapshotError):
        read_snapshot_manifest(tmp_path)


def test_embedding_manifest_gate(tmp_path: Path) -> None:
    (tmp_path / "embedding-manifest.json").write_text(json.dumps({"schema_version": 5}))
    with pytest.raises(SnapshotError) as exc_info:
        read_embedding_manifest(tmp_path)
    assert exc_info.value.code == "SCHEMA_UNSUPPORTED"
