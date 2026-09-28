"""Runtime and provider protocols. `ModelRuntime` is implemented by `OllamaRuntime` (F001),
`EmbeddingProvider` by `OllamaEmbeddingProvider` (F003); `GenerationProvider` arrives in F005."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Protocol

from score_docs_assistant.domain.models import InstalledModel, RuntimeInfo
from score_docs_assistant.domain.snapshots import EmbeddingIdentity


def normalize_tag(tag: str) -> str:
    return tag if ":" in tag else f"{tag}:latest"


class ModelRuntime(Protocol):
    def version(self) -> RuntimeInfo: ...

    def list_models(self) -> list[InstalledModel]: ...

    def pull(self, tag: str) -> Iterator[dict[str, Any]]: ...


class GenerationProvider(Protocol):
    """Chat/completion provider interface. Implemented starting in F005."""


class EmbeddingProvider(Protocol):
    """Local document embedding (FR-007). Implementations MUST NOT truncate inputs silently: an
    input over the model's context bound raises `SnapshotError("EMBEDDING_INPUT_TOO_LONG")`, and
    an unreachable runtime or missing model raises `SnapshotError("EMBEDDING_UNAVAILABLE")`."""

    def identity(self) -> EmbeddingIdentity: ...

    def context_tokens(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
