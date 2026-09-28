"""`doctor`, `models inspect`, and `serve` (startup + every endpoint) never call `/api/pull`
(FR-004, US3 AS4)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import score_docs_assistant.cli.doctor as doctor_module
import score_docs_assistant.cli.models as models_module
from score_docs_assistant.api.app import create_app
from score_docs_assistant.cli.main import cli_app
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.models import ModelProfile, ProfileModel
from score_docs_assistant.models.ollama import OllamaRuntime
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.storage.corpus_probe import FileCorpusProbe

runner = CliRunner()


@pytest.fixture(autouse=True)
def _pull_must_never_be_called(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(self: OllamaRuntime, tag: str) -> None:
        raise AssertionError("pull must never be called outside `models pull`")

    monkeypatch.setattr(OllamaRuntime, "pull", _fail)


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def _write_local_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "model-profiles.yaml").write_text(
        (Path(__file__).parent.parent.parent / "config" / "model-profiles.yaml").read_text()
    )
    config_file = config_dir / "local.yaml"
    config_file.write_text("schema_version: 1\nprofile: local\ndata_dir: ../data\n")
    return config_file


def _fake_ollama(fake_runtime: Callable[[dict | None], httpx.Client]) -> OllamaRuntime:
    return OllamaRuntime("http://127.0.0.1:11434", client=fake_runtime({}))


def test_doctor_never_pulls(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setattr(doctor_module, "build_runtime", lambda config: _fake_ollama(fake_runtime))
    result = runner.invoke(cli_app, ["--config", str(config_file), "doctor"])
    assert result.exit_code == 0, result.output


def test_models_inspect_never_pulls(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setattr(models_module, "build_runtime", lambda config: _fake_ollama(fake_runtime))
    result = runner.invoke(cli_app, ["--config", str(config_file), "models", "inspect"])
    assert result.exit_code == 0, result.output


def test_serve_endpoints_never_pull(
    tmp_path: Path, fake_runtime: Callable[[dict | None], httpx.Client]
) -> None:
    config = AppConfig(data_dir=tmp_path)
    profile = ModelProfile(
        name="local-small",
        models=[
            ProfileModel(role="generation", tag="qwen3:4b-instruct", size_source="t"),
            ProfileModel(role="embedding", tag="nomic-embed-text", size_source="t"),
        ],
    )
    readiness_service = ReadinessService(
        config=config,
        runtime=_fake_ollama(fake_runtime),
        corpus_probe=FileCorpusProbe(tmp_path),
        profile=profile,
        cache_seconds=0,
    )
    app = create_app(config=config, readiness_service=readiness_service)
    client = TestClient(app, base_url="http://127.0.0.1:8080")

    for path in ("/health/live", "/health/ready", "/api/v1/capabilities"):
        response = client.get(path, headers={"host": "127.0.0.1:8080"})
        assert response.status_code in (200, 503)
