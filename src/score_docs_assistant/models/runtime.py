"""Runtime and provider protocols. Declarations only — F001 implements only `ModelRuntime`
(via `OllamaRuntime`); `GenerationProvider`/`EmbeddingProvider` are implemented in F003/F005."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol

from score_docs_assistant.domain.models import InstalledModel, RuntimeInfo


def normalize_tag(tag: str) -> str:
    return tag if ":" in tag else f"{tag}:latest"


class ModelRuntime(Protocol):
    def version(self) -> RuntimeInfo: ...

    def list_models(self) -> list[InstalledModel]: ...

    def pull(self, tag: str) -> Iterator[dict[str, Any]]: ...


class GenerationProvider(Protocol):
    """Chat/completion provider interface. Implemented starting in F005."""


class EmbeddingProvider(Protocol):
    """Embedding provider interface. Implemented starting in F003."""
