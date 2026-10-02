"""`doctor` refresh line (F011 FR-011, contracts/state-file.md)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from score_docs_assistant.diagnostics.checks import check_refresh_state
from score_docs_assistant.refresh.models import RefreshRun, RefreshState
from score_docs_assistant.refresh.state import state_path, write_state

NOW = datetime(2026, 10, 2, 10, 15, tzinfo=UTC)


def _write(data: Path, outcome: str, success: datetime | None = None) -> None:
    run = RefreshRun(
        started_at=NOW,
        finished_at=NOW,
        outcome=outcome,  # type: ignore[arg-type]
        reason="gate failed: coverage_drop",
        active_after="20261002T101500Z-1a2b3c4d",
    )
    write_state(data, RefreshState(last_run=run, last_success_at=success))


def test_not_run_is_info(tmp_path: Path) -> None:
    check = check_refresh_state(tmp_path)
    assert (check.status, check.code) == ("info", "REFRESH_NOT_RUN")


@pytest.mark.parametrize("outcome", ["up-to-date", "activated"])
def test_success_is_ok(tmp_path: Path, outcome: str) -> None:
    _write(tmp_path, outcome, NOW)
    check = check_refresh_state(tmp_path)
    assert (check.status, check.code) == ("ok", "REFRESH_OK")
    assert check.details["active_snapshot"] == "20261002T101500Z-1a2b3c4d"


def test_held_is_warning_with_reason_and_last_success(tmp_path: Path) -> None:
    _write(tmp_path, "held", datetime(2026, 10, 1, tzinfo=UTC))
    check = check_refresh_state(tmp_path)
    assert (check.status, check.code) == ("warning", "REFRESH_HELD")
    assert "coverage_drop" in check.message and "2026-10-01T00:00:00Z" in check.message


def test_failed_never_succeeded(tmp_path: Path) -> None:
    _write(tmp_path, "failed")
    check = check_refresh_state(tmp_path)
    assert (check.status, check.code) == ("warning", "REFRESH_FAILED")
    assert "Last success: never" in check.message


def test_invalid_state_is_warning(tmp_path: Path) -> None:
    state_path(tmp_path).write_text("garbage")
    check = check_refresh_state(tmp_path)
    assert (check.status, check.code) == ("warning", "REFRESH_STATE_INVALID")
    assert check.status != "failure"
