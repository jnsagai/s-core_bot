"""Source registry validation (FR-001, FR-002; contracts/registry.md)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.sources.registry import GitSource, load_registry

REPO_ROOT = Path(__file__).parent.parent.parent
REAL_REGISTRY = REPO_ROOT / "config" / "sources.yaml"


def _base() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(REAL_REGISTRY.read_text())
    return data


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    (tmp_path / "parser-profiles").mkdir(exist_ok=True)
    (tmp_path / "parser-profiles" / "s-core.yaml").write_text(
        (REPO_ROOT / "config" / "parser-profiles" / "s-core.yaml").read_text()
    )
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def _errors(tmp_path: Path, data: dict[str, Any]) -> list[tuple[str, str]]:
    with pytest.raises(ConfigError) as exc_info:
        load_registry(_write(tmp_path, data))
    return exc_info.value.errors


def _paths(errors: list[tuple[str, str]]) -> list[str]:
    return [p for p, _ in errors]


def test_committed_registry_is_valid() -> None:
    registry = load_registry(REAL_REGISTRY)
    ids = [s.source_id for s in registry.sources]
    assert ids == ["score-platform", "score-process", "score-platform-needs", "score-process-needs"]
    assert isinstance(registry.sources[0], GitSource)
    assert len(registry.sha256) == 64


def test_unknown_top_level_key(tmp_path: Path) -> None:
    data = _base()
    data["surprise"] = 1
    assert "surprise" in _paths(_errors(tmp_path, data))


def test_unknown_source_key(tmp_path: Path) -> None:
    data = _base()
    data["sources"][0]["refs"] = "main"
    assert "sources.0.refs" in _paths(_errors(tmp_path, data))


def test_unknown_limits_key(tmp_path: Path) -> None:
    data = _base()
    data["limits"]["max_bytes"] = 1
    assert "limits.max_bytes" in _paths(_errors(tmp_path, data))


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/eclipse-score/score.git",
        "ssh://github.com/eclipse-score/score.git",
        "file:///tmp/repo",
        "git@github.com:eclipse-score/score.git",
        "https://user:token@github.com/eclipse-score/score.git",
        "https://github.com/eclipse-score/score.git?x=1",
        "https://github.com/eclipse-score/score.git#frag",
        "https://github.com:8443/eclipse-score/score.git",
        "https://evil.example/eclipse-score/score.git",
    ],
)
def test_bad_repository_urls(tmp_path: Path, url: str) -> None:
    data = _base()
    data["sources"][0]["repository"] = url
    assert "sources.0.repository" in _paths(_errors(tmp_path, data))


def test_bad_export_url(tmp_path: Path) -> None:
    data = _base()
    data["sources"][2]["url"] = "http://eclipse-score.github.io/score/main/needs.json"
    assert "sources.2.url" in _paths(_errors(tmp_path, data))


def test_uppercase_host_and_explicit_443_accepted(tmp_path: Path) -> None:
    data = _base()
    data["sources"][0]["repository"] = "https://GitHub.com:443/eclipse-score/score.git"
    load_registry(_write(tmp_path, data))


def test_duplicate_source_id(tmp_path: Path) -> None:
    data = _base()
    data["sources"].append(copy.deepcopy(data["sources"][0]))
    assert any("duplicate" in r for _, r in _errors(tmp_path, data))


def test_bad_glob(tmp_path: Path) -> None:
    data = _base()
    data["sources"][0]["include"] = ["docs/[ab].rst"]
    assert "sources.0.include.0" in _paths(_errors(tmp_path, data))


def test_empty_include(tmp_path: Path) -> None:
    data = _base()
    data["sources"][0]["include"] = []
    assert "sources.0.include" in _paths(_errors(tmp_path, data))


def test_associated_source_must_be_git(tmp_path: Path) -> None:
    data = _base()
    data["sources"][2]["associated_source"] = "score-process-needs"
    assert "sources.2.associated_source" in _paths(_errors(tmp_path, data))


def test_associated_source_must_exist(tmp_path: Path) -> None:
    data = _base()
    data["sources"][2]["associated_source"] = "nope"
    assert "sources.2.associated_source" in _paths(_errors(tmp_path, data))


def test_associated_source_requires_docs_root(tmp_path: Path) -> None:
    data = _base()
    del data["sources"][2]["docs_root"]
    assert "sources.2.docs_root" in _paths(_errors(tmp_path, data))


def test_abbreviated_sha_ref_rejected(tmp_path: Path) -> None:
    data = _base()
    data["sources"][0]["ref"] = "e2373d8"
    assert "sources.0.ref" in _paths(_errors(tmp_path, data))


def test_full_sha_ref_accepted(tmp_path: Path) -> None:
    data = _base()
    data["sources"][0]["ref"] = "e2373d822fc2f6e9a3f8a0538904f3faa39309ea"
    load_registry(_write(tmp_path, data))


def test_missing_parser_profile_file(tmp_path: Path) -> None:
    data = _base()
    data["sources"][0]["parser_profile"] = "unknown-profile"
    assert "sources.0.parser_profile" in _paths(_errors(tmp_path, data))


@pytest.mark.parametrize("key", ["max_text_file_bytes", "max_sync_bytes", "read_timeout_seconds"])
def test_non_positive_limits(tmp_path: Path, key: str) -> None:
    data = _base()
    data["limits"][key] = 0
    assert f"limits.{key}" in _paths(_errors(tmp_path, data))


def test_text_cap_above_sync_cap_rejected(tmp_path: Path) -> None:
    data = _base()
    data["limits"]["max_text_file_bytes"] = data["limits"]["max_sync_bytes"] + 1
    assert "limits.max_text_file_bytes" in _paths(_errors(tmp_path, data))


def test_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text("sources: [unclosed\n")
    with pytest.raises(ConfigError):
        load_registry(path)
