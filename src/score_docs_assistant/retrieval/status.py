"""Per-snapshot cache of the semantic status (FR-014, clarification Q3).

A status is reused for at most `ttl_seconds` and dropped immediately when a query embedding
fails, so a runtime that went away (or a changed model) is noticed on the next request.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from score_docs_assistant.domain.snapshots import SemanticStatus

StatusResult = tuple[SemanticStatus, str, list[str]]


class SemanticStatusCache:
    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._items: dict[str, tuple[float, StatusResult]] = {}
        self._lock = threading.Lock()

    def get(self, snapshot_id: str, compute: Callable[[], StatusResult]) -> StatusResult:
        now = self._clock()
        with self._lock:
            cached = self._items.get(snapshot_id)
            if cached is not None and now - cached[0] < self._ttl:
                return cached[1]
        result = compute()
        with self._lock:
            self._items[snapshot_id] = (now, result)
        return result

    def peek(self, snapshot_id: str) -> StatusResult | None:
        with self._lock:
            cached = self._items.get(snapshot_id)
        return None if cached is None else cached[1]

    def invalidate(self, snapshot_id: str) -> None:
        with self._lock:
            self._items.pop(snapshot_id, None)
