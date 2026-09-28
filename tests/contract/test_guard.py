"""HostOriginGuard hostile matrix (research.md R8, contracts/http-api.md Guard, SC-003)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

from score_docs_assistant.api.guard import HostOriginGuard, default_static_get_paths

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


# F006 static-GET exemption (specs/006-local-web-ui/research.md R5, FR-011a, A-034).


@pytest.fixture
def static_client() -> TestClient:
    guarded: Callable[[Scope, Receive, Send], Awaitable[None]] = HostOriginGuard(
        _downstream_app,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=ALLOWED_ORIGINS,
        bound_port=BOUND_PORT,
        static_get_paths=default_static_get_paths,
    )
    return TestClient(guarded)


@pytest.mark.parametrize("path", ["/", "/assets/index-abc123.js"])
def test_cross_site_static_get_exempted(static_client: TestClient, path: str) -> None:
    response = static_client.get(
        path, headers={"host": "127.0.0.1:8080", "sec-fetch-site": "cross-site"}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/capabilities", "/health/ready"])
def test_cross_site_api_and_health_never_exempted(static_client: TestClient, path: str) -> None:
    response = static_client.get(
        path, headers={"host": "127.0.0.1:8080", "sec-fetch-site": "cross-site"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CROSS_SITE_REQUEST"


def test_cross_site_static_get_exemption_is_get_only(static_client: TestClient) -> None:
    response = static_client.post(
        "/", headers={"host": "127.0.0.1:8080", "sec-fetch-site": "cross-site"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CROSS_SITE_REQUEST"


def test_static_get_exemption_still_enforces_host(static_client: TestClient) -> None:
    response = static_client.get(
        "/", headers={"host": "attacker.example", "sec-fetch-site": "cross-site"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HOST_NOT_ALLOWED"


def test_without_static_get_paths_no_exemption_applies(client: TestClient) -> None:
    """The default guard (no static_get_paths passed) has no exemption — F001 behaviour
    unchanged for every existing caller that does not opt in."""
    response = client.get("/", headers={"host": "127.0.0.1:8080", "sec-fetch-site": "cross-site"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CROSS_SITE_REQUEST"
