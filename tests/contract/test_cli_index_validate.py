"""`index validate` CLI contract (FR-016, FR-022, US3 AS1). Mocked provider."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from score_docs_assistant.cli.main import cli_app
from tests.helpers.cli import build_args, invoke, prepare, runner, use_provider
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.snapshot_env import make_env


def _snapshot(env, monkeypatch) -> str:  # type: ignore[no-untyped-def]
    prepare(env, monkeypatch)
    result = invoke(env, *build_args(env, "--json"))
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout.strip().splitlines()[-1])["snapshot_id"]


def _mtimes(directory: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in directory.rglob("*")}


def test_help_first_line() -> None:
    result = runner.invoke(cli_app, ["index", "validate", "--help"])
    assert (
        "Validates a snapshot offline; may query the local runtime for model identity "
        "(never embeds)." in " ".join(result.output.split())
    )


def test_valid_snapshot_exit_0_and_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    snapshot = _snapshot(env, monkeypatch)
    provider = FakeEmbeddingProvider()
    use_provider(monkeypatch, provider)
    directory = env.data / "snapshots" / snapshot
    before = _mtimes(directory)
    result = invoke(env, "index", "validate", "--snapshot", snapshot)
    assert result.exit_code == 0, result.output
    assert "integrity ok" in result.stdout and "semantic: enabled" in result.stdout
    assert _mtimes(directory) == before
    assert list((env.data / "reports").glob(f"validate-{snapshot}-*.json"))
    assert provider.calls == []


@pytest.mark.parametrize(
    ("provider", "semantic"),
    [
        (FakeEmbeddingProvider(digest="7" * 64), "disabled"),
        (FakeEmbeddingProvider(mode="unreachable"), "unverified"),
    ],
)
def test_semantic_warnings_still_exit_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: FakeEmbeddingProvider, semantic: str
) -> None:
    env = make_env(tmp_path)
    snapshot = _snapshot(env, monkeypatch)
    use_provider(monkeypatch, provider)
    result = invoke(env, "index", "validate", "--snapshot", snapshot, "--json")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["semantic"] == semantic


def test_integrity_failure_exit_1_names_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path)
    snapshot = _snapshot(env, monkeypatch)
    target = env.data / "snapshots" / snapshot / "reports" / "coverage.json"
    os.chmod(target, 0o644)
    with target.open("a") as handle:
        handle.write(" ")
    result = invoke(env, "index", "validate", "--snapshot", snapshot)
    assert result.exit_code == 1
    assert "reports/coverage.json" in result.stdout


def test_unknown_and_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    _snapshot(env, monkeypatch)
    result = invoke(env, "index", "validate", "--snapshot", "nope")
    assert result.exit_code == 1 and "SNAPSHOT_NOT_FOUND" in result.stderr
    assert invoke(env, "index", "validate").exit_code == 2
