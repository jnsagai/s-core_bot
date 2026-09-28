"""`sources validate` / `sources sync` CLI contract (FR-009, FR-024; contracts/cli.md)."""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from typer.testing import CliRunner

import score_docs_assistant.cli.sources as sources_cli
from score_docs_assistant.cli.main import cli_app

runner = CliRunner()
REPO_ROOT = Path(__file__).parent.parent.parent
REGISTRY = REPO_ROOT / "config" / "sources.yaml"


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    (tmp_path / "config" / "parser-profiles").mkdir(parents=True)
    (tmp_path / "config" / "parser-profiles" / "s-core.yaml").write_text(
        (REPO_ROOT / "config" / "parser-profiles" / "s-core.yaml").read_text()
    )
    return tmp_path


def _forbid_processes_and_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_process(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no subprocess expected")

    def no_socket(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no socket expected")

    monkeypatch.setattr(subprocess, "run", no_process)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    monkeypatch.setattr(socket.socket, "connect", no_socket)


def test_validate_real_registry_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    _forbid_processes_and_sockets(monkeypatch)
    result = runner.invoke(cli_app, ["sources", "validate", "--config", str(REGISTRY)])
    assert result.exit_code == 0, result.output


def test_validate_reports_dotted_paths(isolated: Path) -> None:
    data = yaml.safe_load(REGISTRY.read_text())
    data["sources"][0]["ref"] = "e2373d8"
    bad = isolated / "config" / "sources.yaml"
    bad.write_text(yaml.safe_dump(data))
    result = runner.invoke(cli_app, ["sources", "validate", "--config", str(bad)])
    assert result.exit_code == 2
    assert "sources.0.ref: abbreviated commit SHAs are not allowed" in result.output


def test_sync_help_states_network_use() -> None:
    result = runner.invoke(cli_app, ["sources", "sync", "--help"])
    lines = [line.strip() for line in result.output.splitlines() if line.strip()]
    assert "Uses the network" in lines[1]


def test_sync_invalid_registry_exit_2(isolated: Path) -> None:
    bad = isolated / "bad.yaml"
    bad.write_text("schema_version: 2\n")
    result = runner.invoke(cli_app, ["sources", "sync", "--config", str(bad)])
    assert result.exit_code == 2


def test_sync_json_shape_with_export_only_registry(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = yaml.safe_load(REGISTRY.read_text())
    registry["sources"] = [
        {**registry["sources"][2], "associated_source": None, "docs_root": None, "required": True}
    ]
    path = isolated / "config" / "sources.yaml"
    path.write_text(yaml.safe_dump(registry))
    body = json.dumps({"current_version": "0.1", "versions": {"0.1": {"needs": {}}}}).encode()
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    monkeypatch.setattr(sources_cli, "build_http_client", lambda: httpx.Client(transport=transport))
    result = runner.invoke(cli_app, ["sources", "sync", "--config", str(path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["network_used"] is True
    assert payload["lock_path"].endswith("source-lock.json")
    (entry,) = payload["sources"]
    assert entry["source_id"] == "score-platform-needs" and entry["status"] == "ok"
    assert set(entry) == {"source_id", "status", "revision", "files", "skipped", "bytes", "failure"}
    assert (isolated / "data" / "source-lock.json").is_file()
