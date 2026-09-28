"""Single-writer ingest lock (FR-011): `flock(LOCK_EX | LOCK_NB)` on `data/locks/ingest.lock`.

The kernel releases the lock when the holding process exits for any reason, so a crashed build
never leaves a stale lock behind.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from score_docs_assistant.domain.errors import SnapshotError


class IngestLock:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "locks" / "ingest.lock"
        self._fd: int | None = None

    def acquire(self) -> IngestLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise SnapshotError(
                "BUILD_BUSY", "another build, import or activation is running; retry afterwards"
            ) from None
        self._fd = fd
        return self

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> IngestLock:
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()
