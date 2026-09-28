"""Export download: host allowlist on every hop, byte cap, no truncation (FR-007, SC-003)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import httpx
import pytest

from score_docs_assistant.sources.http_fetch import FetchedBytes, FetchError, fetch_export

HOSTS = ["eclipse-score.github.io", "github.com"]
URL = "https://eclipse-score.github.io/score/main/needs.json"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _fetch(client: httpx.Client, url: str = URL, max_bytes: int = 1000) -> FetchedBytes:
    return fetch_export(
        url,
        allowed_hosts=HOSTS,
        max_bytes=max_bytes,
        connect_timeout=1,
        read_timeout=1,
        client=client,
    )


def test_success_returns_bytes_hash_size() -> None:
    body = b'{"x": 1}'
    result = _fetch(_client(lambda r: httpx.Response(200, content=body)))
    assert result.data == body
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.size == len(body)


def test_over_cap_fails_without_partial_result() -> None:
    with pytest.raises(FetchError) as exc_info:
        _fetch(_client(lambda r: httpx.Response(200, content=b"a" * 1001)))
    assert exc_info.value.code == "TOO_LARGE"


def test_redirect_to_allowlisted_https_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/score/main/needs.json":
            return httpx.Response(301, headers={"location": "https://github.com/moved.json"})
        return httpx.Response(200, content=b"{}")

    assert _fetch(_client(handler)).final_url == "https://github.com/moved.json"


@pytest.mark.parametrize(
    "location",
    ["https://evil.example/needs.json", "http://github.com/needs.json", "file:///etc/passwd"],
)
def test_redirect_off_allowlist_refused(location: str) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": location})

    with pytest.raises(FetchError) as exc_info:
        _fetch(_client(handler))
    assert exc_info.value.code == "REDIRECT_REFUSED"
    assert requested == [URL]


def test_too_many_redirects() -> None:
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(302, headers={"location": f"https://github.com/{counter['n']}"})

    with pytest.raises(FetchError) as exc_info:
        _fetch(_client(handler))
    assert exc_info.value.code == "TOO_MANY_REDIRECTS"
    assert counter["n"] == 4


def test_initial_url_validated_before_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    with pytest.raises(FetchError) as exc_info:
        _fetch(_client(handler), url="https://evil.example/needs.json")
    assert exc_info.value.code == "URL_NOT_ALLOWED"


def test_timeout_and_http_error() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchError) as exc_info:
        _fetch(_client(timeout))
    assert exc_info.value.code == "TIMEOUT"
    with pytest.raises(FetchError) as http_error:
        _fetch(_client(lambda r: httpx.Response(404)))
    assert http_error.value.code == "HTTP_404"
