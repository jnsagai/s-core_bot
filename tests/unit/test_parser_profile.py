"""Parser profile validation and hashing (FR-011, FR-017)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.sources.profile import load_profile, profile_hash

REAL_PROFILE = Path(__file__).parent.parent.parent / "config" / "parser-profiles" / "s-core.yaml"


def _base() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(REAL_PROFILE.read_text())
    return data


def _load(tmp_path: Path, data: dict[str, Any]) -> Any:
    path = tmp_path / "p.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_profile(path)


def test_committed_profile_loads() -> None:
    profile = load_profile(REAL_PROFILE)
    assert len(profile.need_types) == 41
    assert "derived_from" in profile.link_options
    assert profile.literal_directives["uml"] == "plantuml"
    assert profile.name == "s-core"


def test_hash_stable_across_loads() -> None:
    assert profile_hash(load_profile(REAL_PROFILE)) == profile_hash(load_profile(REAL_PROFILE))


def test_hash_changes_when_entry_changes(tmp_path: Path) -> None:
    data = _base()
    base = profile_hash(_load(tmp_path, data))
    data["link_options"].append("verifies")
    assert profile_hash(_load(tmp_path, data)) != base


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["need_types"].append("std_req"),  # duplicate
        lambda d: d["dynamic_directives"].append("std_req"),  # in two directive lists
        lambda d: d["need_types"].append("bad name!"),  # invalid name
        lambda d: d.__setitem__("extra", 1),  # unknown key
        lambda d: d.__setitem__("need_types", []),  # empty
        lambda d: d["dynamic_roles"].append("need"),  # role in two lists
    ],
)
def test_invalid_profiles_rejected(tmp_path: Path, mutate: Any) -> None:
    data = _base()
    mutate(data)
    with pytest.raises(ConfigError):
        _load(tmp_path, data)
