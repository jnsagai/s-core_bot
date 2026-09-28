"""Single-writer ingest lock across processes (FR-011)."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.locks import IngestLock
from score_docs_assistant.storage.pins import ExclusiveHold, Pin, is_pinned
from tests.helpers.procs import hold_ingest_lock, hold_pin, kill9


def test_second_holder_gets_build_busy_and_sigkill_releases(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proc = hold_ingest_lock(data, tmp_path)
    try:
        with pytest.raises(SnapshotError) as exc_info:
            IngestLock(data).acquire()
        assert exc_info.value.code == "BUILD_BUSY"
    finally:
        kill9(proc)
    with IngestLock(data) as lock:
        assert lock.held


def test_pin_blocks_exclusive_probe_until_process_killed(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proc = hold_pin(data, "snap-a", tmp_path)
    try:
        assert is_pinned(data, "snap-a")
        assert ExclusiveHold.try_acquire(data, "snap-a") is None
    finally:
        kill9(proc)
    assert not is_pinned(data, "snap-a")


def test_in_process_pin_release(tmp_path: Path) -> None:
    pin = Pin(tmp_path, "s")
    other = Pin(tmp_path, "s")  # shared locks coexist
    other.close()
    pin.close()
    hold = ExclusiveHold.try_acquire(tmp_path, "s")
    assert hold is not None
    hold.release(remove_file=True)
    assert not (tmp_path / "pins" / "s.pin").exists()
    assert not is_pinned(tmp_path, "never-pinned")
