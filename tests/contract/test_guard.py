"""HostOriginGuard hostile matrix (research.md R8, contracts/http-api.md Guard, SC-003)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

from score_docs_assistant.api.guard import HostOriginGuard

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
ALLOWED_ORIGINS = ["http://127.0.0.1:8080", "http://localhost:8080"]
BOUND_PORT = 8080


async def _downstream_app(scope: Scope, receive: Receive, send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.fixture
def client() -> TestClient:
    guarded: Callable[[Scope, Receive, Send], Awaitable[None]] = HostOriginGuard(
        _downstream_app,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
        bound_port=BOUND_PORT,
    )
    return TestClient(guarded)


@pytest.mark.parametrize("bad_host", ["attacker.example", "localhost:9999", "127.0.0.1.nip.io"])
def test_disallowed_host_rejected(client: TestClient, bad_host: str) -> None:
    response = client.get("/anything", headers={"host": bad_host})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HOST_NOT_ALLOWED"


@pytest.mark.parametrize("method", ["GET", "POST", "OPTIONS"])
def test_disallowed_origin_rejected(client: TestClient, method: str) -> None:
    headers = {"host": "127.0.0.1:8080", "origin": "https://evil.example"}
    response = client.request(method, "/anything", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_origin_null_rejected(client: TestClient) -> None:
    response = client.get("/anything", headers={"host": "127.0.0.1:8080", "origin": "null"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_cross_site_without_origin_rejected(client: TestClient) -> None:
    response = client.get(
        "/anything", headers={"host": "127.0.0.1:8080", "sec-fetch-site": "cross-site"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CROSS_SITE_REQUEST"


def test_allowed_origin_gets_exact_acao_and_vary(client: TestClient) -> None:
    response = client.get(
        "/anything", headers={"host": "127.0.0.1:8080", "origin": "http://127.0.0.1:8080"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"
    assert response.headers["vary"] == "Origin"


def test_allowed_origin_preflight_options(client: TestClient) -> None:
    response = client.options(
        "/anything", headers={"host": "127.0.0.1:8080", "origin": "http://127.0.0.1:8080"}
    )
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"
    assert response.headers["access-control-allow-methods"] == "GET, POST"
    assert response.headers["access-control-allow-headers"] == "Content-Type"


def test_no_origin_cli_request_allowed(client: TestClient) -> None:
    response = client.get("/anything", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_error_envelope_shape(client: TestClient) -> None:
    response = client.get("/anything", headers={"host": "attacker.example"})
    payload = response.json()
    error = payload["error"]
    assert set(error) == {"code", "message", "request_id", "retryable"}
    assert error["retryable"] is False
