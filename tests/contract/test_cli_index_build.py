"""`index build` CLI contract (FR-009, FR-022, LOC-003, LOC-006). Mocked provider."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from score_docs_assistant.cli.main import cli_app
from tests.helpers.cli import build_args, invoke, prepare, runner
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.snapshot_env import make_env


def test_help_first_line_states_network_use() -> None:
    result = runner.invoke(cli_app, ["index", "build", "--help"])
    assert result.exit_code == 0
    assert (
        "Builds a snapshot offline; uses only the local embedding runtime (no downloads)."
        in " ".join(result.output.split())
    )


def test_json_result_and_exit_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch)
    result = invoke(env, *build_args(env, "--json"))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert set(payload) == {
        "snapshot_id",
        "state",
        "semantic",
        "counts",
        "embedded",
        "activated",
        "duration_seconds",
        "network_used",
    }
    assert payload["state"] == "validated" and payload["activated"] is False
    assert payload["network_used"] == "loopback-embedding-only"
    assert "stage normalizing" in result.stderr


def test_progress_never_contains_document_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch)
    result = invoke(env, *build_args(env))
    assert result.exit_code == 0
    for phrase in ("watchdog", "Short requirement", "wheel speed", "Both sources repeat"):
        assert phrase not in result.stderr
        assert phrase not in result.stdout


def test_runtime_unreachable_exit_1_suggests_lexical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch, FakeEmbeddingProvider(mode="unreachable"))
    result = invoke(env, *build_args(env))
    assert result.exit_code == 1
    assert "EMBEDDING_UNAVAILABLE" in result.stderr
    assert "--lexical-only" in result.stderr


def test_lexical_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    provider = prepare(env, monkeypatch, FakeEmbeddingProvider(mode="unreachable"))
    result = invoke(env, *build_args(env, "--lexical-only", "--json"))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["semantic"] == "absent" and payload["network_used"] == "none"
    snapshot = env.data / "snapshots" / payload["snapshot_id"]
    assert not (snapshot / "embeddings.f32").exists()
    conn = sqlite3.connect(f"file:{snapshot / 'corpus.sqlite'}?mode=ro", uri=True)
    assert conn.execute(
        "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'watchdog'"
    ).fetchone()[0]
    assert provider.calls == [] and provider.identity_calls == 0


def test_missing_lock_is_usage_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch)
    env.lock_path.unlink()
    result = invoke(env, *build_args(env))
    assert result.exit_code in (1, 2)
    assert result.exit_code != 0


def test_activate_flag_activates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    prepare(env, monkeypatch)
    result = invoke(env, *build_args(env, "--activate", "--json"))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["activated"] is True and payload["state"] == "active"
