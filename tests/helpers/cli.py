"""Invoke the CLI against a `SnapshotEnv` with the fake embedding provider (mocked)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.snapshot_env import PROFILES, SnapshotEnv, write_model_lock

runner = CliRunner()


def config_file(env: SnapshotEnv) -> Path:
    path = env.data.parent / "app.yaml"
    path.write_text(f"schema_version: 1\ndata_dir: {env.data}\n")
    return path


def use_provider(monkeypatch: pytest.MonkeyPatch, provider: FakeEmbeddingProvider) -> None:
    monkeypatch.setattr(runtime_factory, "build_embedding_provider", lambda config: provider)


def invoke(env: SnapshotEnv, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(cli_app, ["--config", str(config_file(env)), *args])


def build_args(env: SnapshotEnv, *extra: str) -> list[str]:
    return [
        "index",
        "build",
        "--source-lock",
        str(env.lock_path),
        "--profiles-dir",
        str(PROFILES),
        *extra,
    ]


def prepare(env: SnapshotEnv, monkeypatch: pytest.MonkeyPatch, provider=None):  # type: ignore[no-untyped-def]
    provider = provider or FakeEmbeddingProvider()
    write_model_lock(env.data, provider.digest)
    use_provider(monkeypatch, provider)
    return provider
