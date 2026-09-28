"""Evidence endpoints under `/api/v1` (specs/004-hybrid-search/contracts/http-api.md).

Handlers are plain `def`, so Starlette runs them in its threadpool; the SearchService does
blocking SQLite/NumPy/HTTP work. Every call is admitted through the service's concurrency gate
(429 when full) and bound to one pinned snapshot. Bodies are never logged.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from score_docs_assistant.domain.errors import SearchError
from score_docs_assistant.domain.retrieval import (
    CitationRecord,
    LookupResponse,
    RelationshipsResponse,
    SearchRequest,
    SearchResponse,
    SnapshotsResponse,
    SourcesResponse,
)
from score_docs_assistant.domain.snapshots import ChunkKind
from score_docs_assistant.retrieval.query import valid_snapshot_id
from score_docs_assistant.retrieval.service import CHUNK_KINDS, MAX_ID_LENGTH, SearchService


class SearchBody(BaseModel):
    """HTTP request body; unknown fields (URLs, model names, options) are rejected."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=100_000)
    snapshot_id: str | None = None
    limit: int | None = Field(default=None, ge=1)
    sources: list[str] = Field(default_factory=list, max_length=32)
    kinds: list[ChunkKind] = Field(default_factory=list, max_length=6)


def _request_id(request: Request) -> str:
    state = getattr(request, "state", None)
    return str(getattr(state, "request_id", "")) if state is not None else ""


def _error(request: Request, status: int, code: str, message: str, retryable: bool) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": _request_id(request),
                "retryable": retryable,
            }
        },
    )


def _only(*allowed: str):  # type: ignore[no-untyped-def]
    """Dependency rejecting query parameters a route does not define (FR-016)."""

    def check(request: Request) -> None:
        unknown = sorted(set(request.query_params) - set(allowed))
        if unknown:
            raise SearchError("QUERY_INVALID", f"unknown query parameter(s): {unknown}")

    return Depends(check)


def _check_snapshot(snapshot_id: str | None) -> None:
    if snapshot_id is not None and not valid_snapshot_id(snapshot_id):
        raise SearchError("QUERY_INVALID", "snapshot_id has an invalid format")


def register_search_routes(app: FastAPI, service: SearchService) -> None:
    @app.exception_handler(SearchError)
    async def _search_error(request: Request, exc: SearchError) -> JSONResponse:
        return _error(request, exc.http_status, exc.code, exc.message, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        if any(e.get("type") == "json_invalid" for e in errors):
            return _error(
                request, 400, "MALFORMED_REQUEST", "Request body is not valid JSON.", False
            )
        fields = sorted({".".join(str(p) for p in e.get("loc", ())[1:]) for e in errors})
        message = f"Invalid request fields: {fields}"
        if any(f.startswith("kinds") for f in fields):
            message += f"; allowed kinds: {list(CHUNK_KINDS)}"
        return _error(request, 422, "REQUEST_INVALID", message, False)

    @app.post("/api/v1/search", response_model=SearchResponse)
    def search(body: SearchBody) -> SearchResponse:
        _check_snapshot(body.snapshot_id)
        with service.admitted():
            return service.search(
                SearchRequest(
                    query=body.query,
                    snapshot_id=body.snapshot_id,
                    limit=body.limit,
                    sources=body.sources,
                    kinds=body.kinds,
                )
            )

    @app.get(
        "/api/v1/entities",
        response_model=LookupResponse,
        dependencies=[_only("id", "snapshot_id", "source_id")],
    )
    def entities(
        id: Annotated[str, Query(min_length=1, max_length=MAX_ID_LENGTH)],
        snapshot_id: str | None = None,
        source_id: Annotated[str | None, Query(max_length=MAX_ID_LENGTH)] = None,
    ) -> LookupResponse:
        _check_snapshot(snapshot_id)
        with service.admitted():
            return service.lookup(id, snapshot_id=snapshot_id, source_id=source_id)

    @app.get(
        "/api/v1/relationships",
        response_model=RelationshipsResponse,
        dependencies=[_only("key", "snapshot_id", "direction", "limit", "offset")],
    )
    def relationships(
        key: Annotated[str, Query(min_length=1, max_length=MAX_ID_LENGTH)],
        snapshot_id: str | None = None,
        direction: Literal["out", "in", "both"] = "both",
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> RelationshipsResponse:
        _check_snapshot(snapshot_id)
        with service.admitted():
            return service.relationships(
                key, snapshot_id=snapshot_id, direction=direction, limit=limit, offset=offset
            )

    @app.get("/api/v1/snapshots", response_model=SnapshotsResponse, dependencies=[_only()])
    def snapshots() -> SnapshotsResponse:
        with service.admitted():
            return service.snapshots()

    @app.get("/api/v1/sources", response_model=SourcesResponse, dependencies=[_only("snapshot_id")])
    def sources(snapshot_id: str | None = None) -> SourcesResponse:
        _check_snapshot(snapshot_id)
        with service.admitted():
            return service.sources(snapshot_id)

    @app.get(
        "/api/v1/citations/{snapshot_id}/{chunk_id}",
        response_model=CitationRecord,
        dependencies=[_only()],
    )
    def citation(snapshot_id: str, chunk_id: str) -> CitationRecord:
        if not valid_snapshot_id(snapshot_id):
            raise SearchError("SNAPSHOT_NOT_FOUND", "unknown snapshot")
        with service.admitted():
            return service.citation(snapshot_id, chunk_id)
