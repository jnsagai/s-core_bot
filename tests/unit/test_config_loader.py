"""Precedence matrix, unknown env handling, path resolution, and missing-file fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.config.loader import load_config
from score_docs_assistant.domain.errors import ConfigError


def test_precedence_default_file_env_cli(tmp_path: Path) -> None:
    config_file = tmp_path / "local.yaml"
    config_file.write_text("schema_version: 1\nprofile: local\nserver:\n  port: 9000\n")

    effective = load_config(
        config_path=config_file,
        env={"SCORE_ASSISTANT_SERVER__PORT": "9100"},
        cli_overrides={"server.port": 9200},
        cwd=tmp_path,
    )
    assert effective.config.server.port == 9200
    assert effective.sources["server.port"] == "cli"

    effective_env_only = load_config(
        config_path=config_file, env={"SCORE_ASSISTANT_SERVER__PORT": "9100"}, cwd=tmp_path
    )
    assert effective_env_only.config.server.port == 9100
    assert effective_env_only.sources["server.port"] == "env"

    effective_file_only = load_config(config_path=config_file, env={}, cwd=tmp_path)
    assert effective_file_only.config.server.port == 9000
    assert effective_file_only.sources["server.port"] == "file"

    effective_default = load_config(config_path=None, env={}, cwd=tmp_path)
    assert effective_default.config.server.port == 8080
    assert effective_default.sources["server.port"] == "default"


def test_score_assistant_config_env_selects_file(tmp_path: Path) -> None:
    config_file = tmp_path / "from_env.yaml"
    config_file.write_text("schema_version: 1\nprofile: local\nserver:\n  port: 8181\n")

    effective = load_config(
        config_path=None, env={"SCORE_ASSISTANT_CONFIG": str(config_file)}, cwd=tmp_path
    )
    assert effective.config.server.port == 8181
    assert effective.config_file == config_file


def test_unknown_env_var_is_config_error() -> None:
    with pytest.raises(ConfigError) as exc_info:
        load_config(config_path=None, env={"SCORE_ASSISTANT_NOT_A_REAL_KEY": "1"}, cwd=Path("."))
    assert exc_info.value.code == "CONFIG_UNKNOWN_ENV"
    assert exc_info.value.errors[0][0] == "SCORE_ASSISTANT_NOT_A_REAL_KEY"


@pytest.mark.parametrize(
    "special_var",
    ["SCORE_ASSISTANT_CONFIG", "SCORE_ASSISTANT_REAL_RUNTIME", "SCORE_ASSISTANT_REAL_PULL"],
)
def test_special_env_vars_are_never_unknown(special_var: str, tmp_path: Path) -> None:
    value = "1"
    if special_var == "SCORE_ASSISTANT_CONFIG":  # names a file, which must exist (A-061)
        (tmp_path / "app.yaml").write_text("schema_version: 1\n")
        value = "app.yaml"
    load_config(config_path=None, env={special_var: value}, cwd=tmp_path)


def test_relative_path_resolves_against_config_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "local.yaml"
    config_file.write_text("schema_version: 1\nprofile: local\ndata_dir: ../data\n")

    effective = load_config(config_path=config_file, env={}, cwd=tmp_path)
    assert effective.config.data_dir == (tmp_path / "data").resolve()


def test_relative_path_resolves_against_cwd_when_no_file(tmp_path: Path) -> None:
    effective = load_config(config_path=None, env={}, cwd=tmp_path)
    assert effective.config.data_dir == (tmp_path / "data").resolve()


def test_missing_requested_config_file_is_an_error(tmp_path: Path) -> None:
    """A-061: never fall back to the defaults (./data) when the requested file is missing."""
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(ConfigError) as info:
        load_config(config_path=missing, env={}, cwd=tmp_path)
    assert info.value.errors == [("config_file", f"config file not found: {missing}")]


def test_missing_file_from_environment_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(env={"SCORE_ASSISTANT_CONFIG": "nope.yaml"}, cwd=tmp_path)


def test_no_config_requested_still_uses_defaults(tmp_path: Path) -> None:
    effective = load_config(config_path=None, env={}, cwd=tmp_path)
    assert effective.config_file is None
    assert effective.config.server.port == 8080
