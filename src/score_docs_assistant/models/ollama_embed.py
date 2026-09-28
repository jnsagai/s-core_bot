"""Ollama document embeddings over loopback (FR-007, specs/003-snapshot-index/research.md R1).

Ollama silently truncates over-long inputs unless `truncate: false` is sent, in which case it
answers HTTP 400 "the input length exceeds the context length". We always send it and turn that
answer into EMBEDDING_INPUT_TOO_LONG so no input is ever cut without notice.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from score_docs_assistant.config.schema import is_loopback_host
from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import (
    ChunkerConfig,
    EmbeddingIdentity,
    preprocessing_revision,
)

from .runtime import normalize_tag

_TOO_LONG = "exceeds the context length"
# nomic-embed-text task prefix for queries; pairs with the document prefix in ChunkerConfig
# (specs/004-hybrid-search/research.md R3).
QUERY_PREFIX = "search_query: "


class OllamaEmbeddingProvider:
    def __init__(
        self,
        base_url: str,
        model_tag: str,
        *,
        config: ChunkerConfig,
        timeout_seconds: float = 120.0,
        connect_timeout_seconds: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        host = httpx.URL(base_url).host
        if not is_loopback_host(host):
            raise SnapshotError("EMBEDDING_UNAVAILABLE", f"{base_url}: not a loopback runtime")
        self._base_url = base_url.rstrip("/")
        self._tag = normalize_tag(model_tag)
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=timeout_seconds,
                write=timeout_seconds,
                pool=connect_timeout_seconds,
            ),
        )
        self._show: dict[str, Any] | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            response = self._client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise SnapshotError(
                "EMBEDDING_UNAVAILABLE", f"no embedding runtime at {self._base_url}: {exc}"
            ) from exc
        if response.status_code == 400 and _TOO_LONG in response.text:
            raise SnapshotError("EMBEDDING_INPUT_TOO_LONG", response.text.strip())
        if response.status_code == 404:
            raise SnapshotError(
                "EMBEDDING_UNAVAILABLE",
                f"model {self._tag} not installed (run `score-assistant models pull`)",
            )
        if response.status_code != 200:
            raise SnapshotError(
                "EMBEDDING_UNAVAILABLE",
                f"{path} answered {response.status_code}: {response.text[:200]}",
            )
        try:
            return response.json()
        except ValueError as exc:
            raise SnapshotError("EMBEDDING_UNAVAILABLE", f"{path}: non-JSON response") from exc

    def _model_info(self) -> dict[str, Any]:
        if self._show is None:
            data = self._request("POST", "/api/show", {"model": self._tag})
            info = data.get("model_info") if isinstance(data, dict) else None
            if not isinstance(info, dict):
                raise SnapshotError("EMBEDDING_UNAVAILABLE", "/api/show: missing model_info")
            self._show = info
        return self._show

    def _info_int(self, suffix: str) -> int:
        for key, value in self._model_info().items():
            if key.endswith(suffix) and isinstance(value, int):
                return value
        raise SnapshotError("EMBEDDING_UNAVAILABLE", f"/api/show: no *{suffix}")

    def context_tokens(self) -> int:
        return self._info_int(".context_length")

    def identity(self) -> EmbeddingIdentity:
        tags = self._request("GET", "/api/tags")
        models = tags.get("models") if isinstance(tags, dict) else None
        digest = None
        for model in models or []:
            if isinstance(model, dict) and normalize_tag(str(model.get("name"))) == self._tag:
                digest = model.get("digest")
        if not isinstance(digest, str):
            raise SnapshotError(
                "EMBEDDING_UNAVAILABLE",
                f"model {self._tag} not installed (run `score-assistant models pull`)",
            )
        return EmbeddingIdentity(
            provider="ollama",
            model_tag=self._tag,
            model_digest=digest.removeprefix("sha256:"),
            dimension=self._info_int(".embedding_length"),
            preprocessing_revision=preprocessing_revision(self._config),
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        data = self._request(
            "POST", "/api/embed", {"model": self._tag, "input": list(texts), "truncate": False}
        )
        vectors = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise SnapshotError(
                "EMBEDDING_INVALID_VECTOR", "/api/embed returned a wrong number of vectors"
            )
        return [[float(v) for v in vector] for vector in vectors]

    def embed_query(self, query: str) -> list[float]:
        [vector] = self.embed([QUERY_PREFIX + query])
        return vector
