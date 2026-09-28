"""Scripted, mocked `GenerationProvider` for F005 tests (results count as "mocked")."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from score_docs_assistant.domain.answers import GenerationIdentity
from score_docs_assistant.domain.errors import GenerationError
from score_docs_assistant.models.runtime import GenerationResult

LOCKED_GENERATION_DIGEST = "1" * 64

Script = str | dict[str, Any] | Exception | Callable[[Sequence[dict[str, str]]], str]


def answer(status: str, *claims: tuple[str, str, list[str]]) -> dict[str, Any]:
    return {
        "status": status,
        "claims": [{"text": t, "kind": k, "evidence_ids": e} for t, k, e in claims],
    }


@dataclass
class FakeGenerationProvider:
    outputs: list[Script] = field(default_factory=list)
    digest: str = LOCKED_GENERATION_DIGEST
    delay: float = 0.0
    unavailable: str | None = None  # reason when identity/generation must fail
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)
    cancelled: int = 0
    started: asyncio.Event | None = None

    async def identity(self) -> GenerationIdentity:
        if self.unavailable:
            raise GenerationError("GENERATION_UNAVAILABLE", "fake down", reason=self.unavailable)
        return GenerationIdentity(
            provider="ollama", name="qwen3:4b-instruct", digest=self.digest, runtime_version="fake"
        )

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        schema: dict[str, Any],
        temperature: float,
        context_tokens: int,
        output_tokens: int,
    ) -> GenerationResult:
        self.calls.append([dict(m) for m in messages])
        self.requests.append(
            {
                "schema": schema,
                "temperature": temperature,
                "num_ctx": context_tokens,
                "num_predict": output_tokens,
            }
        )
        if self.started is not None:
            self.started.set()
        if self.unavailable:
            raise GenerationError("GENERATION_UNAVAILABLE", "fake down", reason=self.unavailable)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        script = self.outputs.pop(0) if self.outputs else answer("insufficient_evidence")
        if isinstance(script, Exception):
            raise script
        if callable(script):
            script = script(messages)
        text = script if isinstance(script, str) else json.dumps(script)
        return GenerationResult(text=text, truncated=False, prompt_tokens=100, output_tokens=20)
