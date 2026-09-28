"""Outermost middleware: assigns a request id, injects `X-Request-ID`/`Cache-Control: no-store`
on every response, and writes a single body-free JSON access-log line per request to stderr
(constitution VIII: request_id, method, path, status, duration_ms only)."""

from __future__ import annotations

import json
import sys
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        status_holder: dict[str, int] = {}
        started = time.monotonic()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            log_line = {
                "request_id": request_id,
                "method": scope.get("method"),
                "path": scope.get("path"),
                "status": status_holder.get("status"),
                "duration_ms": round(duration_ms, 2),
            }
            print(json.dumps(log_line), file=sys.stderr, flush=True)
