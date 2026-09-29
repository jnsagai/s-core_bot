"""Rotating file log with bounded retention and body-free records (F009 FR-009, OPS-001)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from score_docs_assistant.api.logging import (
    ACCESS_LOGGER,
    RequestContextMiddleware,
    configure_file_log,
)


def test_records_are_body_free_and_retention_is_bounded(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "access.log"
    handler = configure_file_log(log, retention_days=3)
    try:

        async def echo(request):  # type: ignore[no-untyped-def]
            return PlainTextResponse("secret answer text")

        app = RequestContextMiddleware(Starlette(routes=[Route("/q", echo, methods=["POST"])]))
        client = TestClient(app)
        client.post("/q", content=b"secret question text")
        record = json.loads(log.read_text().splitlines()[-1])
        assert set(record) == {"request_id", "method", "path", "status", "duration_ms"}
        assert "secret" not in log.read_text()

        # Force five rollovers and check that at most three rotated files remain.
        for day in range(5):
            handler.rolloverAt = int(time.time()) - 1  # due now
            stamp = time.time() - (5 - day) * 86400
            os.utime(log, (stamp, stamp))
            ACCESS_LOGGER.info('{"day": %d}', day)
        rotated = [p for p in log.parent.iterdir() if p.name != "access.log"]
        assert 1 <= len(rotated) <= 3
    finally:
        ACCESS_LOGGER.removeHandler(handler)
        handler.close()
        ACCESS_LOGGER.setLevel(logging.NOTSET)


def test_no_file_handler_by_default() -> None:
    from logging.handlers import TimedRotatingFileHandler

    # pytest attaches its own capture handlers; only ours must be absent unless configured.
    assert not any(isinstance(h, TimedRotatingFileHandler) for h in ACCESS_LOGGER.handlers)
