"""Runtime and provider protocols. `ModelRuntime` is implemented by `OllamaRuntime` (F001),
`EmbeddingProvider` by `OllamaEmbeddingProvider` (F003); `GenerationProvider` arrives in F005."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from score_docs_assistant.domain.answers import GenerationIdentity
from score_docs_assistant.domain.models import InstalledModel, RuntimeInfo
from score_docs_assistant.domain.snapshots import EmbeddingIdentity


def normalize_tag(tag: str) -> str:
    return tag if ":" in tag else f"{tag}:latest"


class ModelRuntime(Protocol):
    def version(self) -> RuntimeInfo: ...

    def list_models(self) -> list[InstalledModel]: ...

    def pull(self, tag: str) -> Iterator[dict[str, Any]]: ...


@dataclass(frozen=True)
class GenerationResult:
    text: str
    truncated: bool  # output hit the length limit or the raw-size cap
    prompt_tokens: int | None = None
    output_tokens: int | None = None


class GenerationProvider(Protocol):
    """Local structured generation (F005). Implementations send no tools, stream internally so a
    cancelled task closes the runtime connection, and raise `GenerationError`
    ("GENERATION_UNAVAILABLE") when the runtime or model cannot be used."""

    async def identity(self) -> GenerationIdentity: ...

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        schema: dict[str, Any],
        temperature: float,
        context_tokens: int,
        output_tokens: int,
    ) -> GenerationResult: ...


class EmbeddingProvider(Protocol):
    """Local document embedding (FR-007). Implementations MUST NOT truncate inputs silently: an
    input over the model's context bound raises `SnapshotError("EMBEDDING_INPUT_TOO_LONG")`, and
    an unreachable runtime or missing model raises `SnapshotError("EMBEDDING_UNAVAILABLE")`."""

    def identity(self) -> EmbeddingIdentity: ...

    def context_tokens(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, query: str) -> list[float]:
        """Embed one search query with the model's query convention (F004)."""
        ...
