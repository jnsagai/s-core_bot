"""Download a published export (e.g. `needs.json`) within host, protocol and size limits
(FR-007, research R7). Redirects are followed manually so every hop is re-validated against the
allowlist; the body is streamed and abandoned — never truncated — once it exceeds the cap."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from score_docs_assistant.sources.registry import url_problem

MAX_REDIRECTS = 3


class FetchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class FetchedBytes:
    data: bytes
    sha256: str
    size: int
    final_url: str


def fetch_export(
    url: str,
    *,
    allowed_hosts: list[str],
    max_bytes: int,
    connect_timeout: float,
    read_timeout: float,
    client: httpx.Client | None = None,
) -> FetchedBytes:
    if (problem := url_problem(url, allowed_hosts)) is not None:
        raise FetchError("URL_NOT_ALLOWED", f"{url}: {problem}")
    timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
    own_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        current = url
        for hop in range(MAX_REDIRECTS + 1):
            with http.stream("GET", current, follow_redirects=False, timeout=timeout) as response:
                if response.is_redirect:
                    location = urljoin(current, response.headers.get("location", ""))
                    if (problem := url_problem(location, allowed_hosts)) is not None:
                        raise FetchError("REDIRECT_REFUSED", f"redirect to {location}: {problem}")
                    if hop == MAX_REDIRECTS:
                        break
                    current = location
                    continue
                if response.status_code != 200:
                    raise FetchError(
                        f"HTTP_{response.status_code}", f"{current} returned {response.status_code}"
                    )
                digest = hashlib.sha256()
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError("TOO_LARGE", f"{current} exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    chunks.append(chunk)
                return FetchedBytes(b"".join(chunks), digest.hexdigest(), size, current)
        raise FetchError("TOO_MANY_REDIRECTS", f"more than {MAX_REDIRECTS} redirects from {url}")
    except httpx.TimeoutException as exc:
        raise FetchError("TIMEOUT", f"timed out fetching {url}") from exc
    except httpx.HTTPError as exc:
        raise FetchError("NETWORK_ERROR", f"network error fetching {url}: {exc}") from exc
    finally:
        if own_client:
            http.close()
