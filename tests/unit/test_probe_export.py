"""Conditional export probe for refresh (F011 research R1, FR-002)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from score_docs_assistant.sources.http_fetch import ExportProbe, FetchError, probe_export

HOSTS = ["eclipse-score.github.io", "github.com"]
URL = "https://eclipse-score.github.io/score/main/needs.json"
SEEN: list[httpx.Request] = []


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    def record(request: httpx.Request) -> httpx.Response:
        SEEN.append(request)
        return handler(request)

    SEEN.clear()
    return httpx.Client(transport=httpx.MockTransport(record))


def _probe(
    client: httpx.Client, etag: str | None = '"v1"', modified: str | None = None
) -> ExportProbe:
    return probe_export(
        URL,
        etag=etag,
        last_modified=modified,
        allowed_hosts=HOSTS,
        connect_timeout=1,
        read_timeout=1,
        client=client,
    )


def test_not_modified_sends_validators() -> None:
    result = _probe(
        _client(lambda r: httpx.Response(304)), modified="Thu, 01 Oct 2026 12:51:49 GMT"
    )
    assert result == ExportProbe("not_modified", '"v1"', "Thu, 01 Oct 2026 12:51:49 GMT")
    assert SEEN[0].headers["if-none-match"] == '"v1"'
    assert SEEN[0].headers["if-modified-since"] == "Thu, 01 Oct 2026 12:51:49 GMT"


def test_modified_returns_new_validators() -> None:
    response = httpx.Response(200, headers={"etag": '"v2"'}, content=b"{}")
    result = _probe(_client(lambda r: response))
    assert result == ExportProbe("modified", '"v2"', None)


def test_no_stored_validator_sends_plain_get() -> None:
    _probe(_client(lambda r: httpx.Response(200, headers={"etag": '"v2"'})), etag=None)
    assert "if-none-match" not in SEEN[0].headers


def test_server_without_validators() -> None:
    assert _probe(_client(lambda r: httpx.Response(200))).status == "no_validator"


def test_redirect_to_disallowed_host_refused() -> None:
    client = _client(lambda r: httpx.Response(302, headers={"location": "https://evil.example/x"}))
    with pytest.raises(FetchError) as info:
        _probe(client)
    assert info.value.code == "REDIRECT_REFUSED"


def test_allowed_redirect_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("needs.json"):
            return httpx.Response(301, headers={"location": "/score/main/moved.json"})
        return httpx.Response(304)

    assert _probe(_client(handler)).status == "not_modified"
    assert len(SEEN) == 2


def test_disallowed_url_never_requested() -> None:
    with pytest.raises(FetchError) as info:
        probe_export(
            "https://evil.example/needs.json",
            etag=None,
            last_modified=None,
            allowed_hosts=HOSTS,
            connect_timeout=1,
            read_timeout=1,
            client=_client(lambda r: httpx.Response(200)),
        )
    assert info.value.code == "URL_NOT_ALLOWED" and SEEN == []


def test_server_error() -> None:
    with pytest.raises(FetchError) as info:
        _probe(_client(lambda r: httpx.Response(503)))
    assert info.value.code == "HTTP_503"


def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchError) as info:
        _probe(_client(handler))
    assert info.value.code == "TIMEOUT"
