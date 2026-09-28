"""Deterministic, mocked `EmbeddingProvider` for F003 tests (results count as "mocked")."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass, field

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import (
    ChunkerConfig,
    EmbeddingIdentity,
    preprocessing_revision,
)

FAKE_DIGEST = "0" * 63 + "f"


def fake_vector(text: str, dimension: int) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
        values.extend(v / 2**31 - 1.0 for v in struct.unpack("<8I", digest))
        counter += 1
    values = values[:dimension]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


@dataclass
class FakeEmbeddingProvider:
    dimension: int = 16
    digest: str = FAKE_DIGEST
    context: int = 2048
    mode: str = "ok"  # ok | unreachable | wrong_dimension | nan
    too_long_chars: int | None = None
    config: ChunkerConfig = field(default_factory=ChunkerConfig)
    calls: list[list[str]] = field(default_factory=list)
    identity_calls: int = 0
    truncate_flags: list[bool] = field(default_factory=list)

    def identity(self) -> EmbeddingIdentity:
        self.identity_calls += 1
        if self.mode == "unreachable":
            raise SnapshotError("EMBEDDING_UNAVAILABLE", "fake runtime unreachable")
        return EmbeddingIdentity(
            provider="ollama",
            model_tag="nomic-embed-text:latest",
            model_digest=self.digest,
            dimension=self.dimension,
            preprocessing_revision=preprocessing_revision(self.config),
        )

    def context_tokens(self) -> int:
        if self.mode == "unreachable":
            raise SnapshotError("EMBEDDING_UNAVAILABLE", "fake runtime unreachable")
        return self.context

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        self.truncate_flags.append(False)
        if self.mode == "unreachable":
            raise SnapshotError("EMBEDDING_UNAVAILABLE", "fake runtime unreachable")
        if self.too_long_chars is not None:
            for index, text in enumerate(texts):
                if len(text) > self.too_long_chars:
                    raise SnapshotError("EMBEDDING_INPUT_TOO_LONG", f"input {index} too long")
        vectors = [fake_vector(text, self.dimension) for text in texts]
        if self.mode == "wrong_dimension":
            vectors = [v[:-1] for v in vectors]
        if self.mode == "nan":
            vectors[0][0] = float("nan")
        return vectors

    @property
    def embedded_count(self) -> int:
        return sum(len(c) for c in self.calls)
