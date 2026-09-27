"""Host/Origin/cross-site guard and CORS as pure ASGI middleware.

research.md R8, contracts/http-api.md.

Runs inside `RequestContextMiddleware`, so `scope["state"]["request_id"]` is always already set.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_ALLOWED_METHODS = b"GET, POST"
_ALLOWED_HEADERS = b"Content-Type"


def _split_host_port(value: str) -> tuple[str, int | None]:
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        host = value[1:end]
        rest = value[end + 1 :]
        port = int(rest[1:]) if rest.startswith(":") and rest[1:].isdigit() else None
        return host.lower(), port
    if ":" in value:
        host, _, port_str = value.rpartition(":")
        port = int(port_str) if port_str.isdigit() else None
        return host.lower(), port
    return value.lower(), None


def _host_allowed(host_header: str, allowed_hosts: list[str], bound_port: int) -> bool:
    if not host_header:
        return False
    hostname, port = _split_host_port(host_header)
    for entry in allowed_hosts:
        entry_host, entry_port = _split_host_port(entry)
        if entry_host != hostname:
            continue
        if entry_port is None:
            if port is None or port == bound_port:
                return True
        elif port == entry_port:
            return True
    return False


def _error_body(code: str, message: str, request_id: str) -> bytes:
    return json.dumps(
        {
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "retryable": False,
            }
        }
    ).encode("utf-8")


async def _send_json(
    send: Send, status: int, body: bytes, extra_headers: list[tuple[bytes, bytes]]
) -> None:
    headers = [(b"content-type", b"application/json"), *extra_headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class HostOriginGuard:
    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: list[str],
        allowed_origins: list[str],
        bound_port: int,
    ) -> None:
        self._app = app
        self._allowed_hosts = allowed_hosts
        self._allowed_origins = set(allowed_origins)
        self._bound_port = bound_port

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope["headers"]
        }
        request_id = scope.get("state", {}).get("request_id", "")
        host = headers.get("host", "")
        origin = headers.get("origin")
        sec_fetch_site = headers.get("sec-fetch-site")

        if not _host_allowed(host, self._allowed_hosts, self._bound_port):
            body = _error_body("HOST_NOT_ALLOWED", "Request Host is not allowed.", request_id)
            await _send_json(send, 400, body, [])
            return

        if origin is not None and origin not in self._allowed_origins:
            body = _error_body("ORIGIN_NOT_ALLOWED", "Request origin is not allowed.", request_id)
            await _send_json(send, 403, body, [])
            return

        if sec_fetch_site == "cross-site":
            body = _error_body(
                "CROSS_SITE_REQUEST", "Cross-site requests are not allowed.", request_id
            )
            await _send_json(send, 403, body, [])
            return

        cors_headers: list[tuple[bytes, bytes]] = []
        if origin is not None:
            cors_headers = [
                (b"access-control-allow-origin", origin.encode("latin-1")),
                (b"vary", b"Origin"),
            ]

        if scope["method"] == "OPTIONS" and origin is not None:
            response_headers = [
                *cors_headers,
                (b"access-control-allow-methods", _ALLOWED_METHODS),
                (b"access-control-allow-headers", _ALLOWED_HEADERS),
            ]
            await send({"type": "http.response.start", "status": 204, "headers": response_headers})
            await send({"type": "http.response.body", "body": b""})
            return

        if not cors_headers:
            await self._app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers_out = list(message.get("headers", [])) + cors_headers
                message = {**message, "headers": headers_out}
            await send(message)

        await self._app(scope, receive, send_wrapper)
