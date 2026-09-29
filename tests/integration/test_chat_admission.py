"""Admission, cancellation and deadlines for chat (FR-018–FR-020, SC-005). Mocked providers."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest

from score_docs_assistant.api.app import create_fastapi_app
from score_docs_assistant.domain.answers import ChatRequest
from score_docs_assistant.domain.errors import GenerationError
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import FakeGenerationProvider, answer

GOOD = answer("answered", ("The watchdog supervises task deadlines.", "documented", ["E1"]))


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("admission"))


def test_one_active_four_queued_then_busy(fx: AnswerFixture) -> None:
    async def scenario() -> None:
        generator = FakeGenerationProvider(outputs=[GOOD] * 5, delay=0.3)
        service = fx.service(generator)
        progress: dict[int, list[dict[str, Any]]] = {}

        def run(i: int) -> asyncio.Task[Any]:
            async def emit(event: dict[str, Any]) -> None:
                progress.setdefault(i, []).append(event)

            return asyncio.create_task(
                service.answer(ChatRequest(question="watchdog"), request_id=str(i), progress=emit)
            )

        tasks = [run(0)]
        await asyncio.sleep(0.2)  # first one holds the slot
        tasks += [run(i) for i in range(1, 5)]
        await asyncio.sleep(0.05)
        assert service.queue.active and service.queue.waiting == 4
        with pytest.raises(GenerationError) as exc_info:
            await service.answer(ChatRequest(question="watchdog"), request_id="x")
        assert exc_info.value.code == "CHAT_BUSY" and exc_info.value.retryable
        envelopes = await asyncio.gather(*tasks)
        assert all(e.status == "answered" for e in envelopes)
        assert [e["position"] for e in (progress[i][0] for i in range(1, 5))] == [1, 2, 3, 4]
        assert [e["stage"] for e in progress[0]][:2] == ["searching", "generating"]

    asyncio.run(scenario())


def test_cancel_releases_slot_within_two_seconds(fx: AnswerFixture) -> None:
    async def scenario() -> None:
        generator = FakeGenerationProvider(outputs=[GOOD, GOOD], delay=30)
        generator.started = asyncio.Event()
        service = fx.service(generator)
        running = asyncio.create_task(
            service.answer(ChatRequest(question="watchdog"), request_id="a")
        )
        await asyncio.wait_for(generator.started.wait(), 10)
        started = time.monotonic()
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        assert time.monotonic() - started < 2
        assert generator.cancelled == 1 and not service.queue.active
        generator.delay = 0
        envelope = await service.answer(ChatRequest(question="watchdog"), request_id="b")
        assert envelope.status == "answered"

    asyncio.run(scenario())


async def _asgi_call(
    app: Any,
    body: dict[str, Any],
    accept: str,
    disconnect_after: float,
    path: str = "/api/v1/chat",
) -> list[dict[str, Any]]:
    """Drive the ASGI app directly and disconnect the client after a delay."""
    sent: list[dict[str, Any]] = []
    payload = json.dumps(body).encode()
    delivered = False
    disconnect_at = time.monotonic() + disconnect_after

    async def receive() -> dict[str, Any]:
        # Like a real server: block until the client leaves, then report it immediately
        # (Starlette polls receive() inside an already-cancelled scope).
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}
        remaining = disconnect_at - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (b"host", b"127.0.0.1:8080"),
            (b"content-type", b"application/json"),
            (b"accept", accept.encode()),
        ],
        "client": ("127.0.0.1", 5000),
        "server": ("127.0.0.1", 8080),
        "state": {},
    }
    await asyncio.wait_for(app(scope, receive, send), 10)
    return sent


@pytest.mark.parametrize("accept", ["application/json", "text/event-stream"])
def test_route_disconnect_cancels_generation(fx: AnswerFixture, accept: str) -> None:
    async def scenario() -> None:
        generator = FakeGenerationProvider(outputs=[GOOD], delay=30)
        service = fx.service(generator)
        app = create_fastapi_app(
            config=fx.config(),
            readiness_service=None,  # type: ignore[arg-type]
            search_service=service._search,  # noqa: SLF001
            answer_service=service,
        )
        started = time.monotonic()
        await _asgi_call(app, {"question": "watchdog"}, accept, disconnect_after=0.5)
        await asyncio.sleep(0.1)
        assert time.monotonic() - started < 3
        assert generator.cancelled == 1 and not service.queue.active

    asyncio.run(scenario())


def test_deadline_releases(tmp_path: Path) -> None:
    local = make_answer_fixture(tmp_path)

    async def scenario() -> None:
        generator = FakeGenerationProvider(outputs=[GOOD], delay=5)
        service = local.service(generator, limits={"request_deadline_seconds": 1})
        with pytest.raises(GenerationError) as exc_info:
            await service.answer(ChatRequest(question="watchdog"), request_id="d")
        assert exc_info.value.code == "DEADLINE_EXCEEDED" and exc_info.value.http_status == 504
        assert not service.queue.active and generator.cancelled == 1

    asyncio.run(scenario())
