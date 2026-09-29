"""`POST /api/v1/compare` and `GET /api/v1/snapshots/diff` (specs/007-version-comparison/contracts).

The comparison mirrors chat: JSON by default, or `Accept: text/event-stream` for progress events
and one final validated `comparison` event. A client disconnect cancels the task, which releases
the generation slot and both snapshot pins. Bodies are never logged.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from score_docs_assistant.api.chat_routes import _error_body, _request_id, _sse, _watch_disconnect
from score_docs_assistant.comparison.service import ComparisonService
from score_docs_assistant.domain.comparison import ComparisonRequest, ComparisonResult, SnapshotDiff
from score_docs_assistant.domain.errors import GenerationError, SearchError
from score_docs_assistant.retrieval.service import SearchService


def _no_extra_params(request: Request) -> None:
    unknown = sorted(set(request.query_params) - {"left", "right"})
    if unknown:
        raise SearchError("QUERY_INVALID", f"unknown query parameter(s): {unknown}")


def register_compare_routes(
    app: FastAPI, service: ComparisonService, search: SearchService
) -> None:
    @app.get(
        "/api/v1/snapshots/diff",
        response_model=SnapshotDiff,
        dependencies=[Depends(_no_extra_params)],
    )
    def snapshot_diff(
        left: Annotated[str, Query(min_length=1, max_length=64)],
        right: Annotated[str, Query(min_length=1, max_length=64)],
    ) -> SnapshotDiff:
        with search.admitted():
            return service.diff(left, right)

    @app.post("/api/v1/compare", response_model=ComparisonResult)
    async def compare(request: Request, body: ComparisonRequest) -> Any:
        request_id = _request_id(request)
        if "text/event-stream" in request.headers.get("accept", ""):
            return StreamingResponse(
                _stream(request, body, request_id),
                media_type="text/event-stream",
                headers={"cache-control": "no-store", "x-accel-buffering": "no"},
            )
        task = asyncio.create_task(service.compare(body, request_id=request_id))
        watcher = asyncio.create_task(_watch_disconnect(request, task))
        try:
            result = await task
        except asyncio.CancelledError:
            return JSONResponse(status_code=499, content={})  # client is gone; nothing is read
        finally:
            watcher.cancel()
        return JSONResponse(content=result.model_dump(mode="json"))

    async def _stream(
        request: Request, body: ComparisonRequest, request_id: str
    ) -> AsyncIterator[bytes]:
        events: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

        async def progress(event: dict[str, Any]) -> None:
            await events.put(("progress", event))

        async def run() -> None:
            try:
                result = await service.compare(body, request_id=request_id, progress=progress)
                await events.put(("comparison", result.model_dump(mode="json")))
            except (GenerationError, SearchError) as exc:
                await events.put(("error", _error_body(request, exc)))
            finally:
                await events.put(None)

        task = asyncio.create_task(run())
        watcher = asyncio.create_task(_watch_disconnect(request, task))
        event_id = 0
        try:
            while (item := await events.get()) is not None:
                event_id += 1
                yield _sse(event_id, item[0], item[1])
            event_id += 1
            yield _sse(event_id, "done", {})
        finally:
            watcher.cancel()
            if not task.done():
                task.cancel()
