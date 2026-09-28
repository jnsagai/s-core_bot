"""Generation admission: one active slot and a bounded number of waiters (FR-018, research R7).

Requests beyond the waiting limit are rejected at once (`CHAT_BUSY`, retryable). A cancelled
waiter or holder releases its place immediately, so an aborted request never blocks the next.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from score_docs_assistant.domain.errors import GenerationError

PositionCallback = Callable[[int], Awaitable[None]]


class GenerationQueue:
    def __init__(self, max_waiting: int) -> None:
        self._max_waiting = max_waiting
        self._active = False
        self._waiters: list[asyncio.Future[None]] = []

    @property
    def waiting(self) -> int:
        return len(self._waiters)

    @property
    def active(self) -> bool:
        return self._active

    @asynccontextmanager
    async def slot(self, on_queued: PositionCallback | None = None) -> AsyncIterator[None]:
        if self._active or self._waiters:
            if len(self._waiters) >= self._max_waiting:
                raise GenerationError(
                    "CHAT_BUSY", "an answer is being generated and the queue is full; retry shortly"
                )
            future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self._waiters.append(future)
            try:
                if on_queued is not None:
                    await on_queued(len(self._waiters))
                await future
            except BaseException:
                if future in self._waiters:
                    self._waiters.remove(future)
                elif future.done() and not future.cancelled():
                    self._release()  # the slot was handed to us while we were cancelled
                raise
        else:
            self._active = True
        try:
            yield
        finally:
            self._release()

    def _release(self) -> None:
        while self._waiters:
            nxt = self._waiters.pop(0)
            if not nxt.done():
                nxt.set_result(None)  # hand the slot over; _active stays True
                return
        self._active = False
