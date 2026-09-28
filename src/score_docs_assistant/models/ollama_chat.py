"""Ollama structured generation over loopback (specs/005-grounded-chat/research.md R1).

`/api/chat` with a JSON-schema `format`, low temperature, bounded `num_ctx`/`num_predict`, and
`think: false` only when the model advertises the `thinking` capability. No tools are ever sent.
Responses are streamed and accumulated server-side, so cancelling the awaiting task closes the
connection and the runtime stops generating.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import httpx

from score_docs_assistant.config.schema import is_loopback_host
from score_docs_assistant.domain.answers import GenerationIdentity
from score_docs_assistant.domain.errors import GenerationError

from .runtime import GenerationResult, normalize_tag

MAX_RAW_BYTES = 64 * 1024


class OllamaGenerationProvider:
    def __init__(
        self,
        base_url: str,
        model_tag: str,
        *,
        timeout_seconds: float = 120.0,
        connect_timeout_seconds: float = 1.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not is_loopback_host(httpx.URL(base_url).host):
            raise GenerationError(
                "GENERATION_UNAVAILABLE", f"{base_url}: not a loopback runtime", reason="config"
            )
        self._base_url = base_url.rstrip("/")
        self._tag = normalize_tag(model_tag)
        self._injected = client
        self._timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=timeout_seconds,
            write=timeout_seconds,
            pool=connect_timeout_seconds,
        )
        self._capabilities: list[str] | None = None

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        # An async client is bound to the event loop that created it, so one is opened per call
        # (cheap on loopback) unless a test injects its own.
        if self._injected is not None:
            yield self._injected
            return
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            yield client

    async def _json(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            async with self._client() as client:
                response = await client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise GenerationError(
                "GENERATION_UNAVAILABLE",
                f"no generation runtime at {self._base_url}: {exc}",
                reason="runtime_unreachable",
            ) from exc
        if response.status_code == 404:
            raise GenerationError(
                "GENERATION_UNAVAILABLE",
                f"model {self._tag} not installed (run `score-assistant models pull`)",
                reason="model_missing",
            )
        if response.status_code != 200:
            raise GenerationError(
                "GENERATION_UNAVAILABLE",
                f"{path} answered {response.status_code}",
                reason="runtime_error",
            )
        return response.json()

    async def identity(self) -> GenerationIdentity:
        tags = await self._json("GET", "/api/tags")
        digest = next(
            (
                str(m.get("digest", ""))
                for m in (tags.get("models") or [])
                if isinstance(m, dict) and normalize_tag(str(m.get("name"))) == self._tag
            ),
            None,
        )
        if not digest:
            raise GenerationError(
                "GENERATION_UNAVAILABLE",
                f"model {self._tag} not installed (run `score-assistant models pull`)",
                reason="model_missing",
            )
        version = await self._json("GET", "/api/version")
        return GenerationIdentity(
            provider="ollama",
            name=self._tag,
            digest=digest.removeprefix("sha256:"),
            runtime_version=str(version.get("version")) if isinstance(version, dict) else None,
        )

    async def _supports_thinking(self) -> bool:
        if self._capabilities is None:
            show = await self._json("POST", "/api/show", {"model": self._tag})
            caps = show.get("capabilities") if isinstance(show, dict) else None
            self._capabilities = [str(c) for c in caps] if isinstance(caps, list) else []
        return "thinking" in self._capabilities

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        schema: dict[str, Any],
        temperature: float,
        context_tokens: int,
        output_tokens: int,
    ) -> GenerationResult:
        body: dict[str, Any] = {
            "model": self._tag,
            "messages": list(messages),
            "format": schema,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": context_tokens,
                "num_predict": output_tokens,
            },
        }
        if await self._supports_thinking():
            body["think"] = False
        parts: list[str] = []
        size = 0
        truncated = False
        prompt_tokens: int | None = None
        eval_tokens: int | None = None
        try:
            async with (
                self._client() as client,
                client.stream("POST", "/api/chat", json=body) as response,
            ):
                if response.status_code == 404:
                    raise GenerationError(
                        "GENERATION_UNAVAILABLE",
                        f"model {self._tag} not installed",
                        reason="model_missing",
                    )
                if response.status_code != 200:
                    raise GenerationError(
                        "GENERATION_UNAVAILABLE",
                        f"/api/chat answered {response.status_code}",
                        reason="runtime_error",
                    )
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = str((chunk.get("message") or {}).get("content") or "")
                    size += len(piece.encode("utf-8"))
                    if size > MAX_RAW_BYTES:
                        truncated = True
                        break  # closing the stream stops the runtime
                    parts.append(piece)
                    if chunk.get("done"):
                        truncated = chunk.get("done_reason") == "length"
                        prompt_tokens = chunk.get("prompt_eval_count")
                        eval_tokens = chunk.get("eval_count")
        except httpx.HTTPError as exc:
            raise GenerationError(
                "GENERATION_UNAVAILABLE",
                f"generation failed at {self._base_url}: {exc}",
                reason="runtime_unreachable",
            ) from exc
        except json.JSONDecodeError as exc:
            raise GenerationError(
                "GENERATION_UNAVAILABLE", "non-JSON stream from runtime", reason="runtime_error"
            ) from exc
        return GenerationResult(
            text="".join(parts),
            truncated=truncated,
            prompt_tokens=prompt_tokens,
            output_tokens=eval_tokens,
        )
