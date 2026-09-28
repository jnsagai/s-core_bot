"""Ollama runtime client: version/tags probes and streaming model pull.

See specs/001-foundation/research.md R3 for the API surface this implements.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from score_docs_assistant.domain.errors import (
    RuntimeIncompatible,
    RuntimeTimeout,
    RuntimeUnreachable,
)
from score_docs_assistant.domain.models import InstalledModel, RuntimeInfo

from .runtime import normalize_tag

_PULL_TIMEOUT = httpx.Timeout(connect=1.0, read=60.0, write=60.0, pool=1.0)


class OllamaRuntime:
    def __init__(
        self,
        base_url: str,
        *,
        connect_timeout: float = 1.0,
        read_timeout: float = 3.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=connect_timeout, read=read_timeout, write=read_timeout, pool=connect_timeout
            ),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OllamaRuntime:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _get(self, path: str) -> Any:
        try:
            response = self._client.get(path)
        except httpx.TimeoutException as exc:
            raise RuntimeTimeout(
                self._base_url,
                f"No runtime answered at {self._base_url} within the configured timeout.",
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeUnreachable(
                self._base_url, f"No runtime answered at {self._base_url}: {exc}"
            ) from exc
        if response.status_code != 200:
            raise RuntimeIncompatible(f"Unexpected status {response.status_code} from {path}")
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeIncompatible(f"Non-JSON response from {path}") from exc

    def version(self) -> RuntimeInfo:
        data = self._get("/api/version")
        try:
            version = str(data["version"])
        except (KeyError, TypeError) as exc:
            raise RuntimeIncompatible("`/api/version` response missing 'version'") from exc
        return RuntimeInfo(provider="ollama", base_url=self._base_url, version=version)

    def list_models(self) -> list[InstalledModel]:
        data = self._get("/api/tags")
        try:
            raw_models = data["models"]
        except (KeyError, TypeError) as exc:
            raise RuntimeIncompatible("`/api/tags` response missing 'models'") from exc
        models: list[InstalledModel] = []
        try:
            for raw in raw_models:
                details = raw.get("details") or {}
                models.append(
                    InstalledModel(
                        tag=normalize_tag(raw["name"]),
                        digest=raw["digest"],
                        size_bytes=raw.get("size", 0),
                        family=details.get("family"),
                        parameter_size=details.get("parameter_size"),
                        quantization=details.get("quantization_level"),
                        is_remote=bool(raw.get("remote_model") or raw.get("remote_host")),
                    )
                )
        except (KeyError, TypeError, AttributeError) as exc:
            raise RuntimeIncompatible("`/api/tags` entry missing required fields") from exc
        return models

    def pull(self, tag: str) -> Iterator[dict[str, Any]]:
        try:
            with self._client.stream(
                "POST", "/api/pull", json={"name": tag}, timeout=_PULL_TIMEOUT
            ) as response:
                if response.status_code != 200:
                    raise RuntimeIncompatible(
                        f"Unexpected status {response.status_code} from /api/pull"
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise RuntimeIncompatible("Non-JSON line in /api/pull stream") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeTimeout(
                self._base_url, f"No progress from {self._base_url} within timeout."
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeUnreachable(
                self._base_url, f"No runtime answered at {self._base_url}: {exc}"
            ) from exc
