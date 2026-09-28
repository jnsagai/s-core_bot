"""GenerationQueue admission (FR-018, research R7)."""

from __future__ import annotations

import asyncio

import pytest

from score_docs_assistant.answers.queue import GenerationQueue
from score_docs_assistant.domain.errors import GenerationError


def test_one_active_bounded_waiters_positions_and_release() -> None:
    async def scenario() -> None:
        queue = GenerationQueue(max_waiting=2)
        release = asyncio.Event()
        order: list[str] = []
        positions: list[int] = []

        async def job(name: str) -> None:
            async def on_queued(pos: int) -> None:
                positions.append(pos)

            async with queue.slot(on_queued):
                order.append(name)
                await release.wait()

        first = asyncio.create_task(job("a"))
        await asyncio.sleep(0)
        waiters = [asyncio.create_task(job(n)) for n in ("b", "c")]
        await asyncio.sleep(0)
        assert queue.active and queue.waiting == 2 and positions == [1, 2]
        with pytest.raises(GenerationError) as exc_info:
            async with queue.slot():
                pass
        assert exc_info.value.code == "CHAT_BUSY" and exc_info.value.retryable
        release.set()
        await asyncio.gather(first, *waiters)
        assert order == ["a", "b", "c"] and not queue.active and queue.waiting == 0

    asyncio.run(scenario())


def test_cancelled_waiter_and_holder_release() -> None:
    async def scenario() -> None:
        queue = GenerationQueue(max_waiting=1)
        hold = asyncio.Event()

        async def holder() -> None:
            async with queue.slot():
                await hold.wait()

        h = asyncio.create_task(holder())
        await asyncio.sleep(0)
        w = asyncio.create_task(holder())
        await asyncio.sleep(0)
        w.cancel()
        await asyncio.gather(w, return_exceptions=True)
        assert queue.waiting == 0
        h.cancel()
        await asyncio.gather(h, return_exceptions=True)
        assert not queue.active
        async with queue.slot():
            assert queue.active

    asyncio.run(scenario())


def test_exception_releases() -> None:
    async def scenario() -> None:
        queue = GenerationQueue(max_waiting=0)
        with pytest.raises(RuntimeError):
            async with queue.slot():
                raise RuntimeError
        assert not queue.active

    asyncio.run(scenario())
