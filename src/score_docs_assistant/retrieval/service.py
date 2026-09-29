"""SearchService: the single entry point for search, lookup and evidence (CLI and HTTP).

Every call resolves exactly one snapshot (explicit ID, or the active one resolved once), pins it
for the whole call through F003's `FileSnapshotStore`, and reads only through that handle
(FR-013). Per-snapshot derived data (entity index, filter arrays) is cached, but each call still
takes its own pin, so retention can never delete a snapshot that is in use.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SearchError, SnapshotError
from score_docs_assistant.domain.retrieval import (
    CitationRecord,
    DegradedInfo,
    EvidenceResult,
    LookupResponse,
    RelationshipsResponse,
    RetrievalSettings,
    SearchRequest,
    SearchResponse,
    SnapshotsResponse,
    SnapshotSummary,
    SourcesResponse,
    SourceSummary,
)
from score_docs_assistant.domain.snapshots import SemanticStatus
from score_docs_assistant.ingestion.tokens import estimate_tokens
from score_docs_assistant.models.ollama_embed import QUERY_PREFIX
from score_docs_assistant.models.runtime import EmbeddingProvider
from score_docs_assistant.retrieval.exact import EntityIndex, relationships
from score_docs_assistant.retrieval.fusion import FUSION_VERSION, ChunkMeta, fuse
from score_docs_assistant.retrieval.lexical import keyword_candidates
from score_docs_assistant.retrieval.query import excerpt, fts_expression, valid_chunk_id
from score_docs_assistant.retrieval.semantic import RowAttributes, normalize, top_k
from score_docs_assistant.retrieval.status import SemanticStatusCache, StatusResult
from score_docs_assistant.storage.build import chunker_config
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.corpus_probe import QUERYABLE_STATES
from score_docs_assistant.storage.snapshot_store import FileSnapshotHandle, FileSnapshotStore
from score_docs_assistant.storage.validation import SnapshotValidator

T = TypeVar("T")
CHUNK_KINDS = ("prose", "need", "table", "code", "literal", "diagram")
_QUERYABLE = QUERYABLE_STATES
_REASON_FOR_STATUS = {
    "disabled": "embedding_identity_mismatch",
    "unverified": "embedding_runtime_unavailable",
}
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
        self._status = SemanticStatusCache(config.retrieval.semantic_status_ttl_seconds)
        # Test seam: called after the snapshot is pinned, before retrieval (isolation tests).
        self.after_pin: Callable[[str], None] | None = None

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

    # --- search --------------------------------------------------------------------------------

    def _semantic_status(self, handle: FileSnapshotHandle) -> StatusResult:
        def compute() -> StatusResult:
            return SnapshotValidator(
                data_dir=self._config.data_dir,
                embedding_model=self._config.runtime.embedding_model,
                chunker_config=chunker_config(self._config),
                runtime=self._provider,
            ).semantic_status(handle.manifest)

        return self._status.get(handle.snapshot_id, compute)

    def active_semantic_available(self) -> bool | None:
        """For readiness: None when no active snapshot; never embeds."""
        try:
            with self.pinned(None) as handle:
                return self._semantic_status(handle)[0] == "enabled"
        except SearchError:
            return None

    def _validate(self, request: SearchRequest) -> tuple[str, int]:
        query = request.query.strip()
        limits = self._config.limits
        if not query:
            raise SearchError("QUERY_INVALID", "query must not be empty")
        if len(query) > limits.question_characters:
            raise SearchError(
                "QUERY_INVALID", f"query exceeds {limits.question_characters} characters"
            )
        limit = request.limit or self._config.retrieval.evidence_chunks
        if limit > self._config.retrieval.max_limit:
            raise SearchError(
                "QUERY_INVALID", f"limit must be at most {self._config.retrieval.max_limit}"
            )
        return query, limit

    def search(self, request: SearchRequest, *, force_lexical: bool = False) -> SearchResponse:
        started = time.monotonic()
        query, limit = self._validate(request)
        settings = self._config.retrieval
        timings: dict[str, float] = {}

        def lap(name: str, since: float) -> float:
            now = time.monotonic()
            timings[name] = round((now - since) * 1000, 2)
            return now

        with self.pinned(request.snapshot_id) as handle:
            if self.after_pin is not None:
                self.after_pin(handle.snapshot_id)
            conn = handle.corpus()
            index = self.entity_index(handle)
            if unknown := sorted(set(request.sources) - index.sources):
                raise SearchError(
                    "FILTER_INVALID",
                    f"unknown source(s) {unknown}; allowed: {sorted(index.sources)}",
                )
            sources = list(request.sources)
            kinds: list[str] = [str(k) for k in request.kinds]
            mark = time.monotonic()

            exact_entities = [
                (e, kind)
                for e, kind in index.match_query(query)
                if not sources or e.source_id in sources
            ]
            exact_rows: list[tuple[int, str]] = []
            for entity, kind in exact_entities:
                rowid = index.first_chunk.get(entity.key)
                if rowid is not None:
                    exact_rows.append((rowid, kind))
            mark = lap("exact", mark)

            expression, terms_truncated = fts_expression(query)
            keyword = keyword_candidates(
                conn,
                expression,
                limit=settings.lexical_candidates,
                sources=sources,
                kinds=kinds,
            )
            mark = lap("keyword", mark)

            semantic, degraded, status = self._semantic_candidates(
                handle, query, sources, kinds, force_lexical, timings
            )
            mark = time.monotonic()

            rows = {r for r, _ in exact_rows} | set(keyword) | set(semantic)
            meta, details = self._chunk_rows(conn, rows)
            if kinds:
                exact_rows = [(r, k) for r, k in exact_rows if details[r]["kind"] in kinds]
            selected = fuse(
                exact_rows,
                keyword,
                semantic,
                meta,
                settings.fusion_constant,
                limit,
                settings.max_per_document,
            )
            lap("fusion", mark)

            revision_status = {s.source_id: s.revision_status for s in handle.manifest.sources}
            results = []
            for item in selected:
                row = details[item.rowid]
                text, truncated = excerpt(str(row["text"]), settings.excerpt_characters)
                results.append(
                    EvidenceResult(
                        rank=item.rank,
                        chunk_id=str(row["chunk_id"]),
                        snapshot_id=handle.snapshot_id,
                        source_id=str(row["source_id"]),
                        revision=str(row["revision"]),
                        revision_status=revision_status.get(str(row["source_id"]), "pinned"),
                        path=str(row["path"]),
                        origin_path=str(row["origin_path"]),
                        heading_path=row["heading_path"],  # type: ignore[arg-type]
                        line_start=row["line_start"],  # type: ignore[arg-type]
                        line_end=row["line_end"],  # type: ignore[arg-type]
                        kind=str(row["kind"]),
                        entity_keys=row["entity_keys"],  # type: ignore[arg-type]
                        excerpt=text,
                        truncated=truncated,
                        matched_by=item.matched_by,  # type: ignore[arg-type]
                        ranking_value=item.ranking_value,
                    )
                )
            warnings: list[str] = []
            if degraded is not None and degraded.reason != "lexical_requested":
                warnings.append(
                    f"semantic search unavailable ({degraded.reason}): keyword results only"
                )
            if terms_truncated:
                warnings.append("query_terms_truncated: only the first 64 distinct terms were used")
            timings["total"] = round((time.monotonic() - started) * 1000, 2)
            if time.monotonic() - started > self._config.limits.request_deadline_seconds:
                raise SearchError("DEADLINE_EXCEEDED", "search exceeded the request deadline")
            return SearchResponse(
                snapshot_id=handle.snapshot_id,
                status="ok" if results else "no_results",
                mode="lexical" if degraded is not None else "hybrid",
                degraded=degraded,
                semantic_status=status,
                exact_matches=[index.summary(e, k) for e, k in exact_entities],
                results=results,
                warnings=warnings,
                timings_ms=timings,
                retrieval=RetrievalSettings(
                    fusion_version=FUSION_VERSION,
                    lexical_candidates=settings.lexical_candidates,
                    semantic_candidates=settings.semantic_candidates,
                    fusion_constant=settings.fusion_constant,
                    max_per_document=settings.max_per_document,
                ),
            )

    def _semantic_candidates(
        self,
        handle: FileSnapshotHandle,
        query: str,
        sources: list[str],
        kinds: list[str],
        force_lexical: bool,
        timings: dict[str, float],
    ) -> tuple[list[int], DegradedInfo | None, SemanticStatus]:
        if handle.manifest.semantic != "present":
            return (
                [],
                DegradedInfo(reason="snapshot_lexical_only", detail="snapshot has no vectors"),
                "absent",
            )
        status, detail, guidance = self._semantic_status(handle)
        if force_lexical:
            return [], DegradedInfo(reason="lexical_requested"), status
        if status != "enabled" or self._provider is None:
            reason = _REASON_FOR_STATUS.get(status, "embedding_runtime_unavailable")
            return [], DegradedInfo(reason=reason, detail=detail, guidance=guidance), status  # type: ignore[arg-type]
        cap = self._config.index.embedding_max_input_tokens
        if estimate_tokens(QUERY_PREFIX + query) > cap:
            return (
                [],
                DegradedInfo(
                    reason="query_too_long_for_embedding",
                    detail=f"query exceeds the embedding input cap of {cap} estimated tokens",
                ),
                status,
            )
        mark = time.monotonic()
        try:
            raw = self._provider.embed_query(query)
        except SnapshotError as exc:
            self._status.invalidate(handle.snapshot_id)
            reason = (
                "query_too_long_for_embedding"
                if exc.code == "EMBEDDING_INPUT_TOO_LONG"
                else "embedding_runtime_unavailable"
            )
            return [], DegradedInfo(reason=reason, detail=exc.message), status  # type: ignore[arg-type]
        timings["embedding"] = round((time.monotonic() - mark) * 1000, 2)
        matrix = handle.vectors()
        vector = normalize(
            raw, handle.manifest.embedding.dimension if handle.manifest.embedding else 0
        )
        if matrix is None or vector is None:
            self._status.invalidate(handle.snapshot_id)
            return (
                [],
                DegradedInfo(reason="embedding_runtime_unavailable", detail="invalid query vector"),
                status,
            )
        mark = time.monotonic()
        attributes = self._cache.get(
            handle.snapshot_id, "rows", lambda: RowAttributes.load(handle.corpus())
        )
        ranked = top_k(
            matrix,
            vector,
            attributes.mask(sources, kinds),
            self._config.retrieval.semantic_candidates,
        )
        timings["semantic"] = round((time.monotonic() - mark) * 1000, 2)
        return ranked, None, status

    @staticmethod
    def _chunk_rows(
        conn: sqlite3.Connection, rowids: set[int]
    ) -> tuple[dict[int, ChunkMeta], dict[int, dict[str, object]]]:
        meta: dict[int, ChunkMeta] = {}
        details: dict[int, dict[str, object]] = {}
        if not rowids:
            return meta, details
        ordered = sorted(rowids)
        rows = conn.execute(
            "SELECT rowid, chunk_id, document_key, ordinal, source_id, revision, path, "
            "origin_path, heading_path_json, kind, text, line_start, line_end, entity_keys_json, "
            "content_hash "
            f"FROM chunks WHERE rowid IN ({','.join('?' * len(ordered))})",
            ordered,
        ).fetchall()
        for r in rows:
            meta[r[0]] = ChunkMeta(
                document_key=r[2], source_id=r[4], ordinal=r[3], content_hash=r[14]
            )
            details[r[0]] = {
                "chunk_id": r[1],
                "source_id": r[4],
                "revision": r[5],
                "path": r[6],
                "origin_path": r[7],
                "heading_path": json.loads(r[8]),
                "kind": r[9],
                "text": r[10],
                "line_start": r[11],
                "line_end": r[12],
                "entity_keys": json.loads(r[13]),
            }
        return meta, details

    # --- snapshots, sources, citations ---------------------------------------------------------

    def snapshots(self) -> SnapshotsResponse:
        catalog = Catalog.open(self._config.data_dir, create=False)
        if catalog is None:
            return SnapshotsResponse(active=None, snapshots=[])
        with catalog:
            rows = [r for r in catalog.snapshots() if r.state in _QUERYABLE]
            active = catalog.active_id()
        summaries: list[SnapshotSummary] = []
        for row in rows:
            try:
                with self.pinned(row.snapshot_id) as handle:
                    manifest = handle.manifest
                    cached = self._status.peek(row.snapshot_id)
                    summaries.append(
                        SnapshotSummary(
                            snapshot_id=row.snapshot_id,
                            state=row.state,
                            active=row.snapshot_id == active,
                            created_at=row.created_at,
                            semantic=manifest.semantic,
                            semantic_status=(
                                "absent"
                                if manifest.semantic == "absent"
                                else (cached[0] if cached else None)
                            ),
                            chunks=manifest.counts.chunks,
                            documents=manifest.counts.documents,
                            sources=sorted(manifest.source_revisions),
                            limitations=list(manifest.coverage.limitations),
                        )
                    )
            except SearchError:
                continue  # removed or unreadable between listing and pinning
        return SnapshotsResponse(active=active, snapshots=summaries)

    def sources(self, snapshot_id: str | None = None) -> SourcesResponse:
        with self.pinned(snapshot_id) as handle:
            review: dict[str, list[str]] = {}
            for entry in handle.manifest.license_review:
                review.setdefault(entry.source_id, []).append(entry.path)
            return SourcesResponse(
                snapshot_id=handle.snapshot_id,
                sources=[
                    SourceSummary(
                        source_id=s.source_id,
                        kind=s.kind,
                        revision=s.revision,
                        revision_status=s.revision_status,
                        required=s.required,
                        status=s.status,
                        license_review=review.get(s.source_id, []),
                    )
                    for s in handle.manifest.sources
                ],
            )

    def citation(self, snapshot_id: str, chunk_id: str) -> CitationRecord:
        if not valid_chunk_id(chunk_id):
            raise SearchError("CHUNK_NOT_FOUND", "invalid chunk ID")
        with self.pinned(snapshot_id) as handle:
            row = (
                handle.corpus()
                .execute(
                    "SELECT source_id, revision, path, origin_path, heading_path_json, "
                    "line_start, line_end, kind, entity_keys_json, text, continuation "
                    "FROM chunks WHERE chunk_id = ?",
                    (chunk_id,),
                )
                .fetchone()
            )
            if row is None:
                raise SearchError("CHUNK_NOT_FOUND", f"chunk not in snapshot {snapshot_id}")
            status = {s.source_id: s.revision_status for s in handle.manifest.sources}
            return CitationRecord(
                snapshot_id=handle.snapshot_id,
                chunk_id=chunk_id,
                source_id=row[0],
                revision=row[1],
                revision_status=status.get(row[0], "pinned"),
                path=row[2],
                origin_path=row[3],
                heading_path=json.loads(row[4]),
                line_start=row[5],
                line_end=row[6],
                kind=row[7],
                entity_keys=json.loads(row[8]),
                text=row[9],
                continuation=row[10],
            )
