"""`score-assistant doctor` CLI contract (contracts/cli.md, US1 AS1-AS6)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import score_docs_assistant.cli.doctor as doctor_module
from score_docs_assistant.cli.main import cli_app
from score_docs_assistant.models.ollama import OllamaRuntime

FIXTURES = Path(__file__).parent.parent / "fixtures" / "config"
runner = CliRunner()


def _write_local_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "model-profiles.yaml").write_text(
        (Path(__file__).parent.parent.parent / "config" / "model-profiles.yaml").read_text()
    )
    config_file = config_dir / "local.yaml"
    config_file.write_text("schema_version: 1\nprofile: local\ndata_dir: ../data\n")
    return config_file


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def test_healthy_but_unprepared_machine_exits_0(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setattr(
        doctor_module, "build_runtime", lambda config: _fake_ollama(fake_runtime, {})
    )

    result = runner.invoke(cli_app, ["--config", str(config_file), "doctor"])
    assert result.exit_code == 0, result.output


def test_runtime_unreachable_exits_1(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)
    scenario = {"version": {"raise": httpx.ConnectError("refused")}}
    monkeypatch.setattr(
        doctor_module, "build_runtime", lambda config: _fake_ollama(fake_runtime, scenario)
    )

    result = runner.invoke(cli_app, ["--config", str(config_file), "doctor"])
    assert result.exit_code == 1, result.output


@pytest.mark.parametrize(
    "fixture",
    [
        "unknown_top_level_key.yaml",
        "unknown_nested_key.yaml",
        "wrong_type.yaml",
        "cloud_fallback_true.yaml",
        "provider_openai.yaml",
    ],
)
def test_config_error_exits_2_with_no_runtime_call(
    isolated_cwd: Path, fixture: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_called(config: object) -> object:
        raise AssertionError("runtime must not be constructed when config is invalid")

    monkeypatch.setattr(doctor_module, "build_runtime", _fail_if_called)

    result = runner.invoke(cli_app, ["--config", str(FIXTURES / fixture), "doctor"])
    assert result.exit_code == 2, result.output


def test_json_and_text_report_same_checks(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setattr(
        doctor_module, "build_runtime", lambda config: _fake_ollama(fake_runtime, {})
    )

    json_result = runner.invoke(cli_app, ["--config", str(config_file), "doctor", "--json"])
    text_result = runner.invoke(cli_app, ["--config", str(config_file), "doctor"])
    assert json_result.exit_code == text_result.exit_code == 0

    payload = json.loads(json_result.output)
    for key in ("schema_version", "app_version", "generated_at", "exit_code", "config", "checks"):
        assert key in payload
    # F001's schema has no secret-bearing keys, so nothing should have needed masking.
    assert "***" not in json.dumps(payload)

    json_ids_statuses = {(c["id"], c["status"]) for c in payload["checks"]}
    for check_id, _status in json_ids_statuses:
        assert check_id in text_result.output


def _fake_ollama(
    fake_runtime: Callable[[dict | None], httpx.Client], scenario: dict
) -> OllamaRuntime:
    return OllamaRuntime("http://127.0.0.1:11434", client=fake_runtime(scenario))


@pytest.mark.parametrize("outcome", ["held", "failed"])
def test_refresh_warning_never_changes_exit_code(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    """F011 FR-011: a held/failed refresh is a warning; doctor still exits 0 when healthy."""
    from datetime import UTC, datetime

    from score_docs_assistant.refresh.models import RefreshRun, RefreshState
    from score_docs_assistant.refresh.state import write_state

    config_file = _write_local_config(isolated_cwd)
    now = datetime(2026, 10, 2, tzinfo=UTC)
    run = RefreshRun(started_at=now, finished_at=now, outcome=outcome, reason="gate failed: x")  # type: ignore[arg-type]
    write_state(isolated_cwd / "data", RefreshState(last_run=run))
    monkeypatch.setattr(
        doctor_module, "build_runtime", lambda config: _fake_ollama(fake_runtime, {})
    )
    result = runner.invoke(cli_app, ["--config", str(config_file), "doctor", "--json"])
    assert result.exit_code == 0, result.output
    [check] = [c for c in json.loads(result.stdout)["checks"] if c["id"] == "corpus.refresh"]
    assert check["status"] == "warning"
    assert check["code"] == f"REFRESH_{outcome.upper()}"
