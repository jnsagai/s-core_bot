"""OllamaEmbeddingProvider against a mocked HTTP transport (FR-007, research R1). Mocked."""

from __future__ import annotations

import json

import httpx
import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import ChunkerConfig, preprocessing_revision
from score_docs_assistant.models.ollama_embed import OllamaEmbeddingProvider

SHOW = {"model_info": {"nomic-bert.context_length": 2048, "nomic-bert.embedding_length": 3}}
TAGS = {"models": [{"name": "nomic-embed-text:latest", "digest": "ab" * 32}]}


def _provider(handler, base_url: str = "http://127.0.0.1:11434") -> OllamaEmbeddingProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=base_url)
    return OllamaEmbeddingProvider(
        base_url, "nomic-embed-text", config=ChunkerConfig(), client=client
    )


def test_embed_sends_truncate_false_and_list_input() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0, 0.0]] * len(body["input"])})

    vectors = _provider(handler).embed(["a", "b"])
    assert vectors == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    assert seen == [{"model": "nomic-embed-text:latest", "input": ["a", "b"], "truncate": False}]


def test_context_overflow_maps_to_too_long() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "the input length exceeds the context length"})

    with pytest.raises(SnapshotError) as exc_info:
        _provider(handler).embed(["x"])
    assert exc_info.value.code == "EMBEDDING_INPUT_TOO_LONG"


def test_connection_error_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(SnapshotError) as exc_info:
        _provider(handler).embed(["x"])
    assert exc_info.value.code == "EMBEDDING_UNAVAILABLE"


def test_wrong_vector_count_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": []})

    with pytest.raises(SnapshotError) as exc_info:
        _provider(handler).embed(["x"])
    assert exc_info.value.code == "EMBEDDING_INVALID_VECTOR"


def test_identity_combines_tags_and_show() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=TAGS)
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW)
        raise AssertionError(f"unexpected {request.url.path}")

    provider = _provider(handler)
    identity = provider.identity()
    assert identity.model_digest == "ab" * 32
    assert identity.dimension == 3
    assert identity.model_tag == "nomic-embed-text:latest"
    assert identity.preprocessing_revision == preprocessing_revision(ChunkerConfig())
    assert provider.context_tokens() == 2048


def test_missing_model_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": []})

    with pytest.raises(SnapshotError) as exc_info:
        _provider(handler).identity()
    assert exc_info.value.code == "EMBEDDING_UNAVAILABLE"


def test_only_loopback_accepted() -> None:
    with pytest.raises(SnapshotError):
        OllamaEmbeddingProvider("http://10.0.0.5:11434", "m", config=ChunkerConfig())


def test_embed_query_uses_query_prefix_and_no_truncation() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[0.0, 1.0, 0.0]]})

    assert _provider(handler).embed_query("how to build") == [0.0, 1.0, 0.0]
    assert seen[0]["input"] == ["search_query: how to build"]
    assert seen[0]["truncate"] is False
