"""Secrets never appear in doctor output; doctor never pulls or leaves loopback (FR-004, FR-008,
SC-006)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import score_docs_assistant.cli.doctor as doctor_module
from score_docs_assistant.cli.main import cli_app
from score_docs_assistant.models.ollama import OllamaRuntime

runner = CliRunner()
SECRET = "supersecretvalue123"


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


def test_unknown_secret_looking_env_value_never_echoed(
    isolated_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setenv("SCORE_ASSISTANT_API_KEY", SECRET)

    result = runner.invoke(cli_app, ["--config", str(config_file), "doctor"])
    assert result.exit_code == 2
    assert SECRET not in result.output


def test_doctor_never_calls_pull(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)

    def _fail_pull(self: OllamaRuntime, tag: str) -> None:
        raise AssertionError("doctor must never call pull")

    monkeypatch.setattr(OllamaRuntime, "pull", _fail_pull)
    monkeypatch.setattr(
        doctor_module,
        "build_runtime",
        lambda config: OllamaRuntime("http://127.0.0.1:11434", client=fake_runtime({})),
    )

    result = runner.invoke(cli_app, ["--config", str(config_file), "doctor"])
    assert result.exit_code == 0, result.output
