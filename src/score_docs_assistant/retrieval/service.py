"""SearchService: the single entry point for search, lookup and evidence (CLI and HTTP).

Every call resolves exactly one snapshot (explicit ID, or the active one resolved once), pins it
for the whole call through F003's `FileSnapshotStore`, and reads only through that handle
(FR-013). Per-snapshot derived data (entity index, filter arrays) is cached, but each call still
takes its own pin, so retention can never delete a snapshot that is in use.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SearchError, SnapshotError
from score_docs_assistant.domain.retrieval import LookupResponse, RelationshipsResponse
from score_docs_assistant.models.runtime import EmbeddingProvider
from score_docs_assistant.retrieval.exact import EntityIndex, relationships
from score_docs_assistant.storage.snapshot_store import FileSnapshotHandle, FileSnapshotStore

T = TypeVar("T")
_CACHE_SNAPSHOTS = 2
MAX_ID_LENGTH = 256


class _SnapshotCache:
    """Small LRU of per-snapshot derived structures, keyed by (snapshot ID, kind)."""

    def __init__(self) -> None:
        self._items: OrderedDict[tuple[str, str], object] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, snapshot_id: str, kind: str, build: Callable[[], T]) -> T:
        key = (snapshot_id, kind)
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]  # type: ignore[return-value]
        value = build()
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            snapshots = list(dict.fromkeys(k[0] for k in self._items))
            while len(snapshots) > _CACHE_SNAPSHOTS:
                oldest = snapshots.pop(0)
                for stale in [k for k in self._items if k[0] == oldest]:
                    del self._items[stale]
        return value


class SearchService:
    def __init__(
        self,
        *,
        config: AppConfig,
        provider: EmbeddingProvider | None,
        store: FileSnapshotStore | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._store = store or FileSnapshotStore(config.data_dir)
        self._cache = _SnapshotCache()
        self._gate = threading.BoundedSemaphore(config.retrieval.max_concurrent_searches)

    # --- snapshot binding ----------------------------------------------------------------------

    @contextmanager
    def pinned(self, snapshot_id: str | None) -> Iterator[FileSnapshotHandle]:
        try:
            handle = self._store.pin(snapshot_id) if snapshot_id else self._store.pin_active()
        except SnapshotError as exc:
            if exc.code in ("SCHEMA_UNSUPPORTED", "CATALOG_UNREADABLE", "CHECKSUM_MISMATCH"):
                raise SearchError("SNAPSHOT_INCOMPATIBLE", exc.message) from exc
            if snapshot_id is None:
                raise SearchError(
                    "NO_ACTIVE_SNAPSHOT",
                    "no active snapshot; run `score-assistant index build --activate`",
                ) from exc
            raise SearchError("SNAPSHOT_NOT_FOUND", exc.message) from exc
        try:
            yield handle
        finally:
            handle.close()

    @contextmanager
    def admitted(self) -> Iterator[None]:
        """Concurrency gate for the HTTP server: reject at once when full (clarification Q5)."""
        if not self._gate.acquire(blocking=False):
            raise SearchError("SEARCH_BUSY", "too many searches in progress; retry shortly")
        try:
            yield
        finally:
            self._gate.release()

    def entity_index(self, handle: FileSnapshotHandle) -> EntityIndex:
        return self._cache.get(
            handle.snapshot_id, "entities", lambda: EntityIndex(handle.corpus(), handle.manifest)
        )

    # --- lookup --------------------------------------------------------------------------------

    def lookup(
        self, query: str, *, snapshot_id: str | None = None, source_id: str | None = None
    ) -> LookupResponse:
        token = query.strip()
        if not token or len(token) > MAX_ID_LENGTH:
            raise SearchError("QUERY_INVALID", f"ID must be 1..{MAX_ID_LENGTH} characters")
        with self.pinned(snapshot_id) as handle:
            index = self.entity_index(handle)
            if source_id is not None and source_id not in index.sources:
                raise SearchError(
                    "FILTER_INVALID",
                    f"unknown source {source_id!r}; allowed: {sorted(index.sources)}",
                )
            matches = index.match(token, source_id)
            records = [
                index.record(
                    handle.corpus(), entity, kind, self._config.retrieval.excerpt_characters
                )
                for entity, kind in matches
            ]
            return LookupResponse(
                snapshot_id=handle.snapshot_id,
                query=token,
                status="ok" if records else "no_match",
                entities=records,
            )

    def relationships(
        self,
        key: str,
        *,
        snapshot_id: str | None = None,
        direction: str = "both",
        limit: int = 50,
        offset: int = 0,
    ) -> RelationshipsResponse:
        if not key or len(key) > MAX_ID_LENGTH:
            raise SearchError("QUERY_INVALID", f"key must be 1..{MAX_ID_LENGTH} characters")
        with self.pinned(snapshot_id) as handle:
            outgoing, incoming, items = relationships(
                handle.corpus(),
                self.entity_index(handle),
                key,
                direction=direction,
                limit=limit,
                offset=offset,
            )
            return RelationshipsResponse(
                snapshot_id=handle.snapshot_id,
                key=key,
                outgoing_total=outgoing,
                incoming_total=incoming,
                limit=limit,
                offset=offset,
                items=items,
            )
