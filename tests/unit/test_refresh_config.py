"""RefreshConfig defaults and constraints (specs/015-scheduled-refresh/data-model.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import AppConfig, RefreshConfig

REPO_ROOT = Path(__file__).parent.parent.parent


def test_defaults() -> None:
    config = RefreshConfig()
    assert config.max_count_drop == 0.20
    assert config.check_exports is True
    assert AppConfig().refresh == config


@pytest.mark.parametrize("value", [-0.1, 1.0, 1.5])
def test_max_count_drop_bounds(value: float) -> None:
    with pytest.raises(ValidationError):
        RefreshConfig(max_count_drop=value)


def test_zero_drop_allowed() -> None:
    assert RefreshConfig(max_count_drop=0.0).max_count_drop == 0.0


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"refresh": {"interval": "15min"}})


@pytest.mark.parametrize("name", ["local.yaml", "host-runtime.yaml"])
def test_shipped_configs_still_load(name: str) -> None:
    effective = load_config(config_path=REPO_ROOT / "config" / name)
    assert effective.config.refresh == RefreshConfig()
