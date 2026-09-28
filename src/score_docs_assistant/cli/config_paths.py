"""Shared path helper used by every CLI command module (no dependency on `main`/other commands,
to avoid import cycles)."""

from __future__ import annotations

from pathlib import Path


def profiles_path_for(config_path: Path | None) -> Path:
    if config_path is not None:
        return config_path.parent / "model-profiles.yaml"
    return Path("config") / "model-profiles.yaml"
