"""`score-assistant serve` bind validation (contracts/cli.md, FR-010, FR-011)."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

import score_docs_assistant.cli.serve as serve_module
from score_docs_assistant.cli.main import cli_app

runner = CliRunner()


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    return tmp_path


@pytest.fixture(autouse=True)
def _uvicorn_must_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("uvicorn.run must not be called when bind validation fails")

    monkeypatch.setattr(serve_module.uvicorn, "run", _fail)


def _write_local_config(tmp_path: Path, extra: str = "") -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "model-profiles.yaml").write_text(
        (Path(__file__).parent.parent.parent / "config" / "model-profiles.yaml").read_text()
    )
    config_file = config_dir / "local.yaml"
    config_file.write_text(f"schema_version: 1\nprofile: local\ndata_dir: ../data\n{extra}")
    return config_file


def test_non_loopback_host_via_file_exits_2(isolated_cwd: Path) -> None:
    config_file = _write_local_config(isolated_cwd, "server:\n  host: 0.0.0.0\n")
    result = runner.invoke(cli_app, ["--config", str(config_file), "serve"])
    assert result.exit_code == 2, result.output
    assert "public profile" in result.output


def test_non_loopback_host_via_env_exits_2(
    isolated_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setenv("SCORE_ASSISTANT_SERVER__HOST", "0.0.0.0")
    result = runner.invoke(cli_app, ["--config", str(config_file), "serve"])
    assert result.exit_code == 2, result.output
    assert "public profile" in result.output


def test_non_loopback_host_via_cli_flag_exits_2(isolated_cwd: Path) -> None:
    config_file = _write_local_config(isolated_cwd)
    result = runner.invoke(cli_app, ["--config", str(config_file), "serve", "--host", "0.0.0.0"])
    assert result.exit_code == 2, result.output
    assert "public profile" in result.output


def test_port_in_use_exits_1_bind_failed(isolated_cwd: Path) -> None:
    config_file = _write_local_config(isolated_cwd)
    occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupier.bind(("127.0.0.1", 0))
    occupier.listen(1)
    port = occupier.getsockname()[1]
    try:
        result = runner.invoke(
            cli_app, ["--config", str(config_file), "serve", "--port", str(port)]
        )
        assert result.exit_code == 1, result.output
        assert "BIND_FAILED" in result.output
    finally:
        occupier.close()
