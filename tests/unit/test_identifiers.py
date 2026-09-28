"""Request-supplied identifiers are validated before any path is built (checklist CHK006)."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.retrieval.query import valid_chunk_id, valid_snapshot_id
from score_docs_assistant.storage.snapshot_store import FileSnapshotStore


def test_snapshot_id_pattern() -> None:
    assert valid_snapshot_id("20260928T140548Z-7c6a05b3")
    for bad in ("", "../x", "a/b", "20260928T140548Z-7C6A05B3", "20260928T140548Z-7c6a05b3x"):
        assert not valid_snapshot_id(bad)


def test_chunk_id_pattern() -> None:
    assert valid_chunk_id("a" * 64)
    for bad in ("", "A" * 64, "a" * 63, "../" + "a" * 61, "g" * 64):
        assert not valid_chunk_id(bad)


@pytest.mark.parametrize("bad", ["../../escape", "x/y", "..", ""])
def test_pin_rejects_before_touching_disk(tmp_path: Path, bad: str) -> None:
    store = FileSnapshotStore(tmp_path / "data")
    with pytest.raises(SnapshotError) as exc_info:
        store.pin(bad)
    assert exc_info.value.code == "SNAPSHOT_NOT_FOUND"
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "escape.pin").exists()
