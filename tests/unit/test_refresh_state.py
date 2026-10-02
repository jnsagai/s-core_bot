"""`data/refresh-state.json`: atomic replace, invalid files (contracts/state-file.md)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from score_docs_assistant.refresh.models import ExportValidator, RefreshRun, RefreshState
from score_docs_assistant.refresh.state import StateInvalid, read_state, state_path, write_state

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def _state() -> RefreshState:
    return RefreshState(
        last_run=RefreshRun(started_at=NOW, finished_at=NOW, outcome="up-to-date", reason="ok"),
        last_success_at=NOW,
        exports={"x-needs": ExportValidator(url="https://example.invalid/n.json", etag='"1"')},
    )


def test_missing_file_is_none(tmp_path: Path) -> None:
    assert read_state(tmp_path) is None


def test_round_trip(tmp_path: Path) -> None:
    write_state(tmp_path, _state())
    assert read_state(tmp_path) == _state()


def test_replace_leaves_one_file(tmp_path: Path) -> None:
    write_state(tmp_path, _state())
    write_state(tmp_path, _state())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["refresh-state.json"]


def test_invalid_json(tmp_path: Path) -> None:
    state_path(tmp_path).write_text("{not json")
    result = read_state(tmp_path)
    assert isinstance(result, StateInvalid)


def test_invalid_schema(tmp_path: Path) -> None:
    state_path(tmp_path).write_text('{"schema_version": 2}')
    result = read_state(tmp_path)
    assert isinstance(result, StateInvalid)
    assert "invalid" in result.reason
