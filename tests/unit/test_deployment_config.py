"""Container-mode exception to the loopback rules (F009 FR-003, research R3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from score_docs_assistant.config.schema import AppConfig, LoggingConfig
from score_docs_assistant.domain.errors import GenerationError, SnapshotError
from score_docs_assistant.models.ollama_chat import OllamaGenerationProvider
from score_docs_assistant.models.ollama_embed import OllamaEmbeddingProvider
from score_docs_assistant.storage.build import chunker_config

REPO = Path(__file__).parent.parent.parent
CONTAINER: dict[str, Any] = {
    "server": {"host": "0.0.0.0"},
    "runtime": {"base_url": "http://ollama:11434"},
    "deployment": {"mode": "container", "runtime_private_hosts": ["ollama"]},
}


@pytest.fixture
def in_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCORE_ASSISTANT_CONTAINER", "1")


@pytest.fixture(autouse=True)
def native(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCORE_ASSISTANT_CONTAINER", raising=False)


def test_native_defaults_unchanged() -> None:
    config = AppConfig()
    assert config.deployment.mode == "native" and config.runtime_allowed_hosts() == frozenset()
    with pytest.raises(ValidationError, match="loopback"):
        AppConfig(server={"host": "0.0.0.0"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="loopback"):
        AppConfig(runtime={"base_url": "http://ollama:11434"})  # type: ignore[arg-type]


def test_container_mode_needs_the_image_marker() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate(CONTAINER)
    with pytest.raises(ValidationError, match="application image"):
        AppConfig(deployment={"mode": "container"})  # type: ignore[arg-type]


def test_container_mode_inside_the_image(in_image: None) -> None:
    config = AppConfig.model_validate(CONTAINER)
    assert config.server.host == "0.0.0.0"
    assert config.runtime_allowed_hosts() == frozenset({"ollama"})


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"deployment": {"mode": "native"}}, "requires deployment.mode container"),
        (
            {"deployment": {"mode": "container", "runtime_private_hosts": []}},
            "must be loopback or listed",
        ),
        ({"runtime": {"base_url": "http://evil:11434"}}, "must be loopback or listed"),
        (
            {"deployment": {"mode": "container", "runtime_private_hosts": ["Not A Label"]}},
            "DNS label",
        ),
    ],
)
def test_container_mode_rules(in_image: None, override: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        AppConfig.model_validate({**CONTAINER, **override})


def test_private_hosts_in_native_mode_rejected(in_image: None) -> None:
    with pytest.raises(ValidationError, match="requires deployment.mode container"):
        AppConfig(deployment={"runtime_private_hosts": ["ollama"]})  # type: ignore[arg-type]


def test_marker_alone_does_not_open_anything(in_image: None) -> None:
    config = AppConfig()
    assert config.server.host == "127.0.0.1" and config.runtime_allowed_hosts() == frozenset()
    with pytest.raises(ValidationError, match="requires deployment.mode container"):
        AppConfig(server={"host": "0.0.0.0"})  # type: ignore[arg-type]


def test_providers_refuse_non_loopback_unless_allowed() -> None:
    with pytest.raises(GenerationError):
        OllamaGenerationProvider("http://ollama:11434", "qwen3:4b-instruct")
    OllamaGenerationProvider(
        "http://ollama:11434", "qwen3:4b-instruct", allowed_hosts=frozenset({"ollama"})
    )
    cfg = chunker_config(AppConfig())
    with pytest.raises(SnapshotError):
        OllamaEmbeddingProvider("http://ollama:11434", "nomic-embed-text", config=cfg)
    OllamaEmbeddingProvider(
        "http://ollama:11434", "nomic-embed-text", config=cfg, allowed_hosts=frozenset({"ollama"})
    )


def test_logging_retention_bounds() -> None:
    assert LoggingConfig().retention_days == 7
    for bad in (0, 8):
        with pytest.raises(ValidationError):
            LoggingConfig(retention_days=bad)


def test_committed_container_config_loads_in_the_image(in_image: None) -> None:
    from score_docs_assistant.config.loader import load_config

    config = load_config(config_path=REPO / "config" / "container.yaml").config
    assert config.deployment.mode == "container" and config.server.host == "0.0.0.0"
    assert str(config.data_dir) == "/data"


def test_committed_container_config_refused_outside_the_image() -> None:
    from score_docs_assistant.config.loader import load_config
    from score_docs_assistant.domain.errors import ConfigError

    with pytest.raises(ConfigError):
        load_config(config_path=REPO / "config" / "container.yaml")
