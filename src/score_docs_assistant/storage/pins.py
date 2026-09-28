"""Cross-process snapshot pins (FR-014, specs/003-snapshot-index/research.md R8).

A reader holds `flock(LOCK_SH)` on `data/pins/<snapshot_id>.pin` for as long as it uses the
snapshot. Retention probes with `LOCK_EX | LOCK_NB`: failure means pinned. The kernel drops the
shared lock when the reader exits, even by SIGKILL, so no pin can outlive its process.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


def pin_path(data_dir: Path, snapshot_id: str) -> Path:
    return data_dir / "pins" / f"{snapshot_id}.pin"


class Pin:
    """A held shared lock. Close it (or let the process exit) to release."""

    def __init__(self, data_dir: Path, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        path = pin_path(data_dir, snapshot_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fd: int | None = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(self._fd, fcntl.LOCK_SH)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> Pin:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class ExclusiveHold:
    """Retention's exclusive probe. `try_acquire` returns None when the snapshot is pinned."""

    def __init__(self, fd: int, path: Path) -> None:
        self._fd: int | None = fd
        self.path = path

    @classmethod
    def try_acquire(cls, data_dir: Path, snapshot_id: str) -> ExclusiveHold | None:
        path = pin_path(data_dir, snapshot_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        return cls(fd, path)

    def release(self, *, remove_file: bool = False) -> None:
        if remove_file:
            self.path.unlink(missing_ok=True)
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def is_pinned(data_dir: Path, snapshot_id: str) -> bool:
    if not pin_path(data_dir, snapshot_id).exists():
        return False
    hold = ExclusiveHold.try_acquire(data_dir, snapshot_id)
    if hold is None:
        return True
    hold.release()
    return False
