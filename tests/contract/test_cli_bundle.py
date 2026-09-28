"""`bundle export|inspect|import` CLI contract (FR-019, FR-022). Mocked provider for the build;
bundle commands themselves must open no sockets at all."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from score_docs_assistant.cli.main import cli_app
from tests.helpers.cli import build_args, config_file, invoke, prepare, runner
from tests.helpers.snapshot_env import SnapshotEnv, make_env


@pytest.fixture
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(self: socket.socket, address: object) -> None:
        raise AssertionError(f"bundle command opened a socket to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_export_inspect_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch)
    built = invoke(env, *build_args(env, "--json"))
    snapshot = json.loads(built.stdout.strip().splitlines()[-1])["snapshot_id"]
    out = tmp_path / "x.score-bundle.tar.gz"

    monkeypatch.setattr(
        socket.socket,
        "connect",
        lambda self, a: (_ for _ in ()).throw(AssertionError(f"socket {a!r}")),
    )
    refused = invoke(env, "bundle", "export", "--snapshot", snapshot, "--output", str(out))
    assert refused.exit_code == 1 and "LICENSE_REVIEW_REQUIRED" in refused.stderr
    exported = invoke(
        env,
        "bundle",
        "export",
        "--snapshot",
        snapshot,
        "--output",
        str(out),
        "--acknowledge-license-review",
        "test",
        "--json",
    )
    assert exported.exit_code == 0, exported.output
    assert json.loads(exported.stdout)["sha256"]

    inspected = invoke(env, "bundle", "inspect", str(out), "--json")
    assert inspected.exit_code == 0, inspected.output
    summary = json.loads(inspected.stdout)
    assert summary["snapshot_id"] == snapshot
    assert summary["counts"]["chunks"] > 0 and summary["embedding"]["dimension"] == 16
    assert summary["license_acknowledgement"]["reason"] == "test"

    fresh = SnapshotEnv(data=tmp_path / "fresh" / "data", lock_path=tmp_path / "unused.json")
    fresh.data.mkdir(parents=True)
    imported = runner.invoke(
        cli_app, ["--config", str(config_file(fresh)), "bundle", "import", str(out)]
    )
    assert imported.exit_code == 0, imported.output
    assert f"imported {snapshot} (validated, not active)" in imported.stdout
    assert "snapshots activate" in imported.stdout


def test_rejected_import_exit_1(tmp_path: Path, no_sockets: None) -> None:
    env = SnapshotEnv(data=tmp_path / "data", lock_path=tmp_path / "unused.json")
    env.data.mkdir()
    junk = tmp_path / "junk.tar.gz"
    junk.write_bytes(b"not a bundle")
    result = invoke(env, "bundle", "import", str(junk))
    assert result.exit_code == 1 and "BUNDLE_REJECTED" in result.stderr
    result = invoke(env, "bundle", "inspect", str(junk))
    assert result.exit_code == 1
