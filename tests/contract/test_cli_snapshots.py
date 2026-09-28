"""`snapshots list|activate|rollback` CLI contract (FR-013, FR-022). Mocked provider."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.helpers.cli import build_args, invoke, prepare
from tests.helpers.procs import hold_ingest_lock, hold_pin, kill9
from tests.helpers.snapshot_env import make_env


def _build(env, monkeypatch) -> str:  # type: ignore[no-untyped-def]
    result = invoke(env, *build_args(env, "--json"))
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout.strip().splitlines()[-1])["snapshot_id"]


def test_list_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    result = invoke(env, "snapshots", "list")
    assert result.exit_code == 0
    assert "No snapshots" in result.stdout
    assert not (env.data / "catalog.sqlite").exists()


def test_activate_list_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch)
    a = _build(env, monkeypatch)
    assert invoke(env, "snapshots", "activate", a).exit_code == 0
    b = _build(env, monkeypatch)
    result = invoke(env, "snapshots", "activate", b)
    assert result.exit_code == 0, result.output
    assert f"activated {b} (previous: {a})" in result.stderr

    proc = hold_pin(env.data, a, tmp_path)
    try:
        listed = json.loads(invoke(env, "snapshots", "list", "--json").stdout)["snapshots"]
    finally:
        kill9(proc)
    by_id = {s["snapshot_id"]: s for s in listed}
    assert by_id[b]["active"] and by_id[b]["state"] == "active"
    assert by_id[a]["state"] == "retired" and by_id[a]["pinned"] is True
    text = invoke(env, "snapshots", "list").stdout
    assert f"* {b}" in text and "PINNED" in text and "ACTIVATED" in text

    result = invoke(env, "snapshots", "rollback")
    assert result.exit_code == 0, result.output
    assert f"rolled back to {a}" in result.stderr


def test_error_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch)
    result = invoke(env, "snapshots", "rollback")
    assert result.exit_code == 1 and "NO_ROLLBACK_TARGET" in result.stderr
    a = _build(env, monkeypatch)
    result = invoke(env, "snapshots", "activate", "missing-id")
    assert result.exit_code == 1 and "SNAPSHOT_NOT_FOUND" in result.stderr
    target = env.data / "snapshots" / a / "reports" / "coverage.json"
    os.chmod(target, 0o644)
    target.write_text("{}")
    result = invoke(env, "snapshots", "activate", a)
    assert result.exit_code == 1 and "CHECKSUM_MISMATCH" in result.stderr
    assert "coverage.json" in result.stderr
    result = invoke(env, "snapshots", "activate")
    assert result.exit_code == 2


def test_activation_during_build_is_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch)
    a = _build(env, monkeypatch)
    proc = hold_ingest_lock(env.data, tmp_path)
    try:
        result = invoke(env, "snapshots", "activate", a)
    finally:
        kill9(proc)
    assert result.exit_code == 1 and "BUILD_BUSY" in result.stderr


def test_list_and_activate_open_no_foreign_sockets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The autouse network guard blocks non-loopback connects; the fake provider stands in for
    the loopback identity query. Nothing else may open a socket."""
    import socket

    env = make_env(tmp_path)
    provider = prepare(env, monkeypatch)
    a = _build(env, monkeypatch)
    calls_before = len(provider.calls)
    opened: list[object] = []
    real_connect = socket.socket.connect
    monkeypatch.setattr(
        socket.socket, "connect", lambda self, addr: opened.append(addr) or real_connect(self, addr)
    )
    assert invoke(env, "snapshots", "activate", a).exit_code == 0
    assert invoke(env, "snapshots", "list").exit_code == 0
    assert opened == []
    assert len(provider.calls) == calls_before  # identity only, never embeds
