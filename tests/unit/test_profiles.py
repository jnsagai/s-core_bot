"""Model profile loading (config/model-profiles.yaml) and role enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from score_docs_assistant.domain.errors import ProfileNotFound
from score_docs_assistant.models.profiles import get_profile, load_profiles

REPO_ROOT = Path(__file__).parent.parent.parent
PROFILES_PATH = REPO_ROOT / "config" / "model-profiles.yaml"


def test_load_real_profiles_file() -> None:
    profiles = load_profiles(PROFILES_PATH)
    profile = get_profile(profiles, "local-small")
    assert profile.model_for_role("generation").tag == "qwen3:4b-instruct"
    assert profile.model_for_role("embedding").tag == "nomic-embed-text"


def test_unknown_profile_raises() -> None:
    profiles = load_profiles(PROFILES_PATH)
    with pytest.raises(ProfileNotFound):
        get_profile(profiles, "does-not-exist")


def test_unknown_size_is_none(tmp_path: Path) -> None:
    data = {
        "schema_version": 1,
        "profiles": {
            "test-profile": {
                "models": [
                    {"role": "generation", "tag": "foo:latest", "size_source": "unknown"},
                    {"role": "embedding", "tag": "bar:latest", "size_source": "unknown"},
                ]
            }
        },
    }
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.safe_dump(data))
    profiles = load_profiles(path)
    profile = get_profile(profiles, "test-profile")
    assert profile.model_for_role("generation").approx_size_bytes is None


def test_profile_must_have_exactly_one_generation_and_embedding(tmp_path: Path) -> None:
    data = {
        "schema_version": 1,
        "profiles": {
            "bad-profile": {
                "models": [
                    {"role": "generation", "tag": "foo:latest", "size_source": "unknown"},
                    {"role": "generation", "tag": "foo2:latest", "size_source": "unknown"},
                ]
            }
        },
    }
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="exactly one"):
        load_profiles(path)
