"""`sources inspect` CLI contract (FR-009, FR-023, FR-024; contracts/cli.md)."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from score_docs_assistant.cli.main import cli_app
from tests.helpers.git_repos import make_plain_repo
from tests.helpers.pipeline import PROFILES, sync
from tests.helpers.registries import git_source

runner = CliRunner()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = make_plain_repo(
        tmp_path / "repo",
        {"docs/a.rst": ".. feat_req:: A\n   :id: feat_req__a\n", "LICENSE": "x\n"},
    )
    assert sync(tmp_path / "data", [git_source("docs", repo.url)]) == 0
    shutil.copytree(PROFILES, tmp_path / "config" / "parser-profiles")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def _forbid_processes_and_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("inspect must not spawn processes or open sockets")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def test_text_summary_and_report_file(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _forbid_processes_and_sockets(monkeypatch)
    result = runner.invoke(cli_app, ["sources", "inspect", "--lock", "data/source-lock.json"])
    assert result.exit_code == 0, result.output
    assert "docs @ " in result.output and "entities 1" in result.output
    assert "links: resolved 0" in result.output
    reports = list((workspace / "data" / "reports").glob("coverage-*.json"))
    assert len(reports) == 1


def test_json_output(workspace: Path) -> None:
    result = runner.invoke(
        cli_app, ["sources", "inspect", "--lock", "data/source-lock.json", "--json"]
    )
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
    assert set(report) == {"schema_version", "lock_sha256", "processing_hash", "sources", "totals"}
    assert report["sources"][0]["entities"] == 1


def test_output_jsonl(workspace: Path) -> None:
    out = workspace / "out"
    result = runner.invoke(
        cli_app, ["sources", "inspect", "--lock", "data/source-lock.json", "--output", str(out)]
    )
    assert result.exit_code == 0
    entities = [json.loads(line) for line in (out / "entities.jsonl").read_text().splitlines()]
    assert [e["key"] for e in entities] == ["docs:feat_req__a"]
    assert all(e["canonical_version"] == 1 for e in entities)
    assert (out / "documents.jsonl").read_text().count("\n") == 1


def test_invalid_lock_exit_2(workspace: Path) -> None:
    (workspace / "bad.json").write_text("{not json")
    result = runner.invoke(cli_app, ["sources", "inspect", "--lock", "bad.json"])
    assert result.exit_code == 2


def test_unknown_profile_exit_2(workspace: Path) -> None:
    result = runner.invoke(
        cli_app,
        ["sources", "inspect", "--lock", "data/source-lock.json", "--profiles-dir", "nowhere"],
    )
    assert result.exit_code == 2


def test_failed_required_source_exit_1(workspace: Path) -> None:
    lock_path = workspace / "data" / "source-lock.json"
    lock = json.loads(lock_path.read_text())
    lock["sources"][0]["status"] = "failed"
    lock["sources"][0]["failure"] = "GIT_FETCH_FAILED: simulated"
    lock_path.write_text(json.dumps(lock))
    result = runner.invoke(cli_app, ["sources", "inspect", "--lock", "data/source-lock.json"])
    assert result.exit_code == 1
