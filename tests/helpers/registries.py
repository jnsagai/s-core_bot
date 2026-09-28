"""Build `SourceRegistry` objects for tests without the URL/host semantic checks, so fixture
repositories can be reached over `file://` (production `load_registry` rejects that)."""

from __future__ import annotations

from typing import Any

from score_docs_assistant.sources.registry import SourceRegistry

DEFAULT_LIMITS = {
    "max_text_file_bytes": 1_000_000,
    "max_export_bytes": 1_000_000,
    "max_sync_bytes": 50_000_000,
    "connect_timeout_seconds": 5,
    "read_timeout_seconds": 30,
}


def git_source(source_id: str, url: str, **overrides: Any) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "kind": "git",
        "repository": url,
        "ref": "main",
        "include": ["docs/**/*.rst", "docs/**/*.md", "README.md"],
        "exclude": [],
        "authority": "fixture",
        "repository_license": "Apache-2.0",
        "license_policy": "inspect-file-and-repository-notices",
        "required": True,
        "parser_profile": "s-core",
        **overrides,
    }


def export_source(source_id: str, url: str, **overrides: Any) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "kind": "needs-export",
        "url": url,
        "authority": "fixture",
        "repository_license": "Apache-2.0",
        "license_policy": "inspect-file-and-repository-notices",
        "required": False,
        **overrides,
    }


def make_registry(sources: list[dict[str, Any]], **limits: int) -> SourceRegistry:
    return SourceRegistry.model_validate(
        {
            "schema_version": 1,
            "allowed_hosts": ["github.com", "eclipse-score.github.io"],
            "redistribution_allowed_licenses": ["Apache-2.0", "MIT", "CC0-1.0"],
            "limits": {**DEFAULT_LIMITS, **limits},
            "sources": sources,
        }
    )
