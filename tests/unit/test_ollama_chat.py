"""OllamaGenerationProvider over a mocked transport (FR-013, FR-014, research R1). Mocked."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from score_docs_assistant.domain.errors import GenerationError
from score_docs_assistant.models.ollama_chat import MAX_RAW_BYTES, OllamaGenerationProvider

TAGS = {"models": [{"name": "qwen3:4b-instruct", "digest": "sha256:" + "ab" * 32}]}


def _provider(handler, caps=("completion", "thinking")) -> OllamaGenerationProvider:  # type: ignore[no-untyped-def]
    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": list(caps)})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=TAGS)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.34.0"})
        return handler(request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(route), base_url="http://127.0.0.1:11434"
    )
    return OllamaGenerationProvider("http://127.0.0.1:11434", "qwen3:4b-instruct", client=client)


def _stream(*pieces: str, done_reason: str = "stop") -> bytes:
    lines = [json.dumps({"message": {"content": p}, "done": False}) for p in pieces]
    lines.append(
        json.dumps(
            {
                "message": {"content": ""},
                "done": True,
                "done_reason": done_reason,
                "prompt_eval_count": 10,
                "eval_count": 3,
            }
        )
    )
    return ("\n".join(lines) + "\n").encode()


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _generate(provider: OllamaGenerationProvider):  # type: ignore[no-untyped-def]
    return provider.generate(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        schema={"type": "object"},
        temperature=0.1,
        context_tokens=8192,
        output_tokens=900,
    )


def test_request_body_and_accumulation() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=_stream('{"status":', ' "answered"}'))

    result = _run(_generate(_provider(handler)))
    assert result.text == '{"status": "answered"}' and not result.truncated
    assert (result.prompt_tokens, result.output_tokens) == (10, 3)
    body = seen[0]
    assert body["stream"] is True and body["format"] == {"type": "object"}
    assert body["options"] == {"temperature": 0.1, "num_ctx": 8192, "num_predict": 900}
    assert body["think"] is False and "tools" not in body


def test_think_omitted_when_not_advertised() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=_stream("{}"))

    _run(_generate(_provider(handler, caps=("completion",))))
    assert "think" not in seen[0]


def test_length_stop_marks_truncated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_stream('{"sta', done_reason="length"))

    assert _run(_generate(_provider(handler))).truncated is True


def test_raw_size_cap() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_stream("x" * (MAX_RAW_BYTES + 10)))

    result = _run(_generate(_provider(handler)))
    assert result.truncated is True and result.text == ""


def test_identity() -> None:
    identity = _run(_provider(lambda r: httpx.Response(500)).identity())
    assert identity.digest == "ab" * 32 and identity.name == "qwen3:4b-instruct"
    assert identity.runtime_version == "0.34.0"


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")), "runtime_unreachable"),
        (lambda r: httpx.Response(404, json={"error": "model not found"}), "model_missing"),
    ],
)
def test_unavailable(handler, reason: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(GenerationError) as exc_info:
        _run(_generate(_provider(handler)))
    assert exc_info.value.code == "GENERATION_UNAVAILABLE" and exc_info.value.reason == reason


def test_loopback_only() -> None:
    with pytest.raises(GenerationError):
        OllamaGenerationProvider("http://192.168.1.2:11434", "m")
