"""`POST /api/v1/chat` (specs/005-grounded-chat/contracts/http-api.md).

JSON by default; `Accept: text/event-stream` gives progress events and one final validated answer
(never unchecked claim text). A client disconnect cancels the answer task, which releases the
queue slot and closes the runtime stream. Bodies are never logged.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from score_docs_assistant.answers.service import AnswerService
from score_docs_assistant.domain.answers import AnswerEnvelope, ChatRequest
from score_docs_assistant.domain.errors import GenerationError, SearchError

DISCONNECT_POLL_SECONDS = 0.2


def _request_id(request: Request) -> str:
    state = getattr(request, "state", None)
    return str(getattr(state, "request_id", "")) if state is not None else ""


def _error_body(request: Request, exc: GenerationError | SearchError) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "request_id": _request_id(request),
            "retryable": exc.retryable,
        }
    }


def _sse(event_id: int, event: str, data: dict[str, Any]) -> bytes:
    # Compact single-line JSON: document or model text can never inject SSE fields.
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n".encode()


async def _watch_disconnect(request: Request, task: asyncio.Task[Any]) -> None:
    while not task.done():
        if await request.is_disconnected():
            task.cancel()
            return
        await asyncio.sleep(DISCONNECT_POLL_SECONDS)


def register_chat_routes(app: FastAPI, service: AnswerService) -> None:
    @app.exception_handler(GenerationError)
    async def _generation_error(request: Request, exc: GenerationError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=_error_body(request, exc))

    @app.post("/api/v1/chat", response_model=AnswerEnvelope)
    async def chat(request: Request, body: ChatRequest) -> Any:
        request_id = _request_id(request)
        if "text/event-stream" in request.headers.get("accept", ""):
            return StreamingResponse(
                _stream(request, body, request_id),
                media_type="text/event-stream",
                headers={"cache-control": "no-store", "x-accel-buffering": "no"},
            )
        task = asyncio.create_task(service.answer(body, request_id=request_id))
        watcher = asyncio.create_task(_watch_disconnect(request, task))
        try:
            envelope = await task
        except asyncio.CancelledError:
            return JSONResponse(status_code=499, content={})  # client is gone; nothing is read
        finally:
            watcher.cancel()
        return JSONResponse(content=envelope.model_dump(mode="json"))

    async def _stream(request: Request, body: ChatRequest, request_id: str) -> AsyncIterator[bytes]:
        events: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

        async def progress(event: dict[str, Any]) -> None:
            await events.put(("progress", event))

        async def run() -> None:
            try:
                envelope = await service.answer(body, request_id=request_id, progress=progress)
                await events.put(("answer", envelope.model_dump(mode="json")))
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
