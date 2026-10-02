"""`score-assistant refresh` CLI contract (specs/015-scheduled-refresh/contracts/cli.md)."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from score_docs_assistant.cli import refresh as refresh_cli
from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli import sources as sources_cli
from score_docs_assistant.cli.main import cli_app
from tests.helpers.refresh import FILE_GIT, Upstream, commit, make_upstream
from tests.helpers.registries import make_registry
from tests.helpers.snapshot_env import PROFILES

runner = CliRunner()
JSON_KEYS = {
    "started_at",
    "finished_at",
    "outcome",
    "reason",
    "active_before",
    "active_after",
    "candidate",
    "candidate_semantic",
    "checks",
    "synced",
    "lock_changed",
    "revision_changes",
    "gate",
    "timings",
    "network_used",
    "state_path",
}


@pytest.fixture
def up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Upstream:
    upstream = make_upstream(tmp_path)
    assert upstream.export is not None
    monkeypatch.setattr(refresh_cli, "load_registry", lambda path: make_registry(upstream.sources))
    monkeypatch.setattr(sources_cli, "build_git_client", lambda timeout: FILE_GIT)
    monkeypatch.setattr(sources_cli, "build_http_client", upstream.export.client)
    monkeypatch.setattr(runtime_factory, "build_embedding_provider", lambda c: upstream.provider)
    return upstream


def _invoke(up: Upstream, *args: str):  # type: ignore[no-untyped-def]
    config = up.root / "app.yaml"
    config.write_text(f"schema_version: 1\ndata_dir: {up.data}\n")
    return runner.invoke(
        cli_app,
        ["--config", str(config), "refresh", "--profiles-dir", str(PROFILES), *args],
    )


def test_json_contract_and_exit_codes(up: Upstream) -> None:
    first = _invoke(up, "--json")
    assert first.exit_code == 0, first.output
    payload = json.loads(first.stdout.strip().splitlines()[-1])
    assert set(payload) == JSON_KEYS
    assert payload["outcome"] == "activated" and payload["network_used"] is True
    assert payload["state_path"].endswith("refresh-state.json")

    second = json.loads(_invoke(up, "--json").stdout.strip().splitlines()[-1])
    assert second["outcome"] == "up-to-date"


def test_text_output_ends_with_summary(up: Upstream) -> None:
    result = _invoke(up)
    assert result.exit_code == 0
    last = result.stdout.strip().splitlines()[-1]
    assert last.startswith("activated: activated ")
    assert "gate   integrity pass" in result.stdout
    [build] = [line for line in result.stdout.splitlines() if line.startswith("build  ")]
    assert "  validated  semantic present  (" in build


def test_held_exit_code_3(up: Upstream) -> None:
    _invoke(up)
    commit(up.repo, {"docs/extra.rst": "Extra\n=====\n\nSYNTHETIC — extra.\n"})
    result = _invoke(up, "--lexical-only")
    assert result.exit_code == 3
    assert result.stdout.strip().splitlines()[-1] == "held: gate failed: semantic"


def test_busy_exit_code_4(up: Upstream) -> None:
    _invoke(up)
    fd = os.open(up.data / "locks" / "refresh.lock", os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        result = _invoke(up, "--json")
    finally:
        os.close(fd)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["network_used"] is False


def test_failed_exit_code_1(up: Upstream) -> None:
    _invoke(up)
    up.repo.path.rename(up.root / "moved")
    result = _invoke(up)
    assert result.exit_code == 1
    assert "upstream check failed" in result.stdout


def test_output_has_no_document_text(up: Upstream) -> None:
    result = _invoke(up, "--json")
    assert "watchdog" not in result.stdout and "SYNTHETIC" not in result.stdout


def test_invalid_config_exit_code_2(up: Upstream) -> None:
    config = up.root / "bad.yaml"
    config.write_text("schema_version: 1\nrefresh:\n  max_count_drop: 2\n")
    result = runner.invoke(cli_app, ["--config", str(config), "refresh"])
    assert result.exit_code == 2
