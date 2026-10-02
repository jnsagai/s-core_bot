"""Overlapping runs are refused and change nothing (F011 FR-009, US3-AS2)."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from score_docs_assistant.refresh.state import state_path
from score_docs_assistant.storage.locks import IngestLock
from tests.helpers.refresh import commit, files_under, make_upstream


def test_second_refresh_is_busy_and_writes_nothing(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    before = files_under(up.data)
    lock = up.data / "locks" / "refresh.lock"
    fd = os.open(lock, os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        run = up.refresh()
    finally:
        os.close(fd)
    assert run.outcome == "busy" and run.exit_code == 4
    assert files_under(up.data) == before
    assert run.checks == [] and not run.synced


def test_manual_build_in_progress_maps_to_busy(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    good = up.refresh()
    commit(up.repo, {"docs/busy.rst": "Busy\n====\n\nSYNTHETIC — busy.\n"})
    state_before = state_path(up.data).read_bytes()
    with IngestLock(up.data):  # e.g. a manual `index build` holding the single-writer lock
        run = up.refresh()
    assert run.outcome == "busy" and run.exit_code == 4
    assert up.active() == good.candidate
    assert state_path(up.data).read_bytes() == state_before


def test_refresh_after_busy_succeeds(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    commit(up.repo, {"docs/later.rst": "Later\n=====\n\nSYNTHETIC — later.\n"})
    with IngestLock(up.data):
        assert up.refresh().outcome == "busy"
    assert up.refresh().outcome == "activated"
