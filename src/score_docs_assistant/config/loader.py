"""Configuration loading: defaults < file < environment < CLI, with per-key source tracking.

See contracts/config.md for the precedence rules this implements.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin

import yaml
from pydantic import BaseModel, ValidationError

from score_docs_assistant.domain.errors import ConfigError

from .schema import AppConfig

ENV_PREFIX = "SCORE_ASSISTANT_"
_ENV_SPECIAL = {
    "SCORE_ASSISTANT_CONFIG",
    "SCORE_ASSISTANT_CONTAINER",  # set by the application image (F009); not a config value
    "SCORE_ASSISTANT_REAL_RUNTIME",
    "SCORE_ASSISTANT_REAL_PULL",
}
ConfigSource = str  # "default" | "file" | "env" | "cli"

_MISSING = object()


@dataclass(frozen=True)
class EffectiveConfig:
    config: AppConfig
    sources: dict[str, ConfigSource]
    config_file: Path | None


def _unwrap_optional(annotation: Any) -> Any:
    if get_origin(annotation) in (Union, UnionType):
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _leaf_paths(model_cls: type[BaseModel], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for name, field in model_cls.model_fields.items():
        path = f"{prefix}{name}"
        inner = _unwrap_optional(field.annotation)
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            paths |= _leaf_paths(inner, prefix=f"{path}.")
        else:
            paths.add(path)
    return paths


def _flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, prefix=f"{path}."))
        else:
            out[path] = value
    return out


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _get_path(data: Mapping[str, Any], path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _env_to_path(var_name: str) -> str:
    remainder = var_name[len(ENV_PREFIX) :]
    return ".".join(part.lower() for part in remainder.split("__"))


def _convert_pydantic_errors(exc: ValidationError) -> list[tuple[str, str]]:
    return [(".".join(str(p) for p in err["loc"]), err["msg"]) for err in exc.errors()]


def load_config(
    *,
    config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    cwd: Path | None = None,
) -> EffectiveConfig:
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else cwd
    allowed = _leaf_paths(AppConfig)

    file_path = config_path
    if file_path is None:
        env_config_path = env.get("SCORE_ASSISTANT_CONFIG")
        if env_config_path:
            file_path = Path(env_config_path)

    resolved_file: Path | None = None
    merged: dict[str, Any] = {}
    sources: dict[str, ConfigSource] = {}

    if file_path is not None:
        candidate = file_path if file_path.is_absolute() else (cwd / file_path)
        if not candidate.is_file():
            # A requested but missing file is an error, never a silent fallback to the defaults:
            # the defaults point at ./data, so a mistyped path would act on the real data (A-061).
            raise ConfigError([("config_file", f"config file not found: {candidate}")])

    if file_path is not None:
        resolved_file = candidate
        try:
            raw = yaml.safe_load(resolved_file.read_text())
        except yaml.YAMLError as exc:
            raise ConfigError([("config_file", f"invalid YAML: {exc}")]) from exc
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ConfigError([("config_file", "top-level content must be a mapping")])
        for path, value in _flatten(raw).items():
            _set_path(merged, path, value)
            sources[path] = "file"

    env_errors: list[tuple[str, str]] = []
    for var_name, raw_value in env.items():
        if not var_name.startswith(ENV_PREFIX) or var_name in _ENV_SPECIAL:
            continue
        path = _env_to_path(var_name)
        if path not in allowed:
            env_errors.append((var_name, "unknown environment variable"))
            continue
        try:
            value = yaml.safe_load(raw_value)
        except yaml.YAMLError:
            env_errors.append((path, f"invalid value in {var_name}"))
            continue
        _set_path(merged, path, value)
        sources[path] = "env"

    if env_errors:
        raise ConfigError(env_errors, code="CONFIG_UNKNOWN_ENV")

    for path, value in (cli_overrides or {}).items():
        _set_path(merged, path, value)
        sources[path] = "cli"

    base_dir = resolved_file.parent if resolved_file is not None else cwd
    for path_field in ("data_dir", "runtime.models_dir"):
        existing = _get_path(merged, path_field)
        if existing is _MISSING or existing is None:
            continue
        candidate = Path(existing)
        if not candidate.is_absolute():
            _set_path(merged, path_field, str((base_dir / candidate).resolve()))
    if _get_path(merged, "data_dir") is _MISSING:
        default_data_dir = AppConfig.model_fields["data_dir"].default
        _set_path(merged, "data_dir", str((base_dir / default_data_dir).resolve()))
        sources.setdefault("data_dir", "default")

    try:
        config = AppConfig(**merged)
    except ValidationError as exc:
        raise ConfigError(_convert_pydantic_errors(exc)) from exc

    for path in allowed:
        sources.setdefault(path, "default")

    return EffectiveConfig(
        config=config,
        sources=sources,
        config_file=resolved_file,
    )
