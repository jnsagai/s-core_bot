"""Load `config/model-profiles.yaml`."""

from __future__ import annotations

from pathlib import Path

import yaml

from score_docs_assistant.domain.errors import ProfileNotFound
from score_docs_assistant.domain.models import ModelProfile, ProfileModel


def load_profiles(path: Path) -> dict[str, ModelProfile]:
    raw = yaml.safe_load(path.read_text()) or {}
    profiles_raw = raw.get("profiles", {})
    profiles: dict[str, ModelProfile] = {}
    for name, data in profiles_raw.items():
        models = [ProfileModel(**m) for m in data.get("models", [])]
        roles = [m.role for m in models]
        if roles.count("generation") != 1 or roles.count("embedding") != 1:
            raise ValueError(
                f"profile {name!r} must have exactly one generation and one embedding model"
            )
        profiles[name] = ModelProfile(name=name, models=models)
    return profiles


def get_profile(profiles: dict[str, ModelProfile], name: str) -> ModelProfile:
    try:
        return profiles[name]
    except KeyError as exc:
        raise ProfileNotFound(name) from exc
