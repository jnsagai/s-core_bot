"""Refresh records: strict fields and exit-code mapping (specs/015-scheduled-refresh)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from score_docs_assistant.refresh.models import EXIT_CODES, GateCheck, RefreshRun, RefreshState

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def run(outcome: str) -> RefreshRun:
    return RefreshRun(started_at=NOW, finished_at=NOW, outcome=outcome, reason="r")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("outcome", "code"),
    [("up-to-date", 0), ("activated", 0), ("failed", 1), ("held", 3), ("busy", 4)],
)
def test_exit_codes(outcome: str, code: int) -> None:
    assert run(outcome).exit_code == code


def test_exit_code_2_is_reserved_for_config_errors() -> None:
    assert 2 not in EXIT_CODES.values()


def test_unknown_outcome_rejected() -> None:
    with pytest.raises(ValidationError):
        run("approved")


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        GateCheck.model_validate({"id": "semantic", "status": "pass", "detail": "", "x": 1})


def test_state_round_trip() -> None:
    state = RefreshState(last_run=run("held"), last_success_at=NOW)
    assert RefreshState.model_validate_json(state.model_dump_json()) == state
