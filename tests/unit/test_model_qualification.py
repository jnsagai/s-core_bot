"""Model qualification from the lock and a fake runtime (F008 FR-017; mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from score_docs_assistant.qualification.models import qualify

LOCK = {
    "schema_version": 1,
    "profile": "local-small",
    "runtime": {"provider": "ollama", "version": "0.34.0"},
    "models": [
        {
            "role": "generation",
            "tag": "qwen3:4b-instruct",
            "digest": "a" * 64,
            "size_bytes": 1,
            "acquired_at": "x",
        },
        {
            "role": "embedding",
            "tag": "nomic-embed-text:latest",
            "digest": "b" * 64,
            "size_bytes": 1,
            "acquired_at": "x",
        },
    ],
}


def fake(installed_embed: str) -> Any:
    calls: list[str] = []

    def fetch(path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        calls.append(path)
        if path == "/api/tags":
            return {
                "models": [
                    {"name": "qwen3:4b-instruct", "digest": "a" * 64},
                    {"name": "nomic-embed-text:latest", "digest": installed_embed},
                ]
            }
        if path == "/api/version":
            return {"version": "0.34.0"}
        assert path == "/api/show" and body is not None
        return {
            "license": "\n   Apache License\n Version 2.0",
            "details": {
                "family": "qwen3",
                "parameter_size": "4.0B",
                "quantization_level": "Q4_K_M",
            },
            "model_info": {"qwen3.context_length": 262144},
        }

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def test_records_identity_license_and_lock_match(tmp_path: Path) -> None:
    lock = tmp_path / "model-lock.json"
    lock.write_text(json.dumps(LOCK))
    fetch = fake("c" * 64)
    record = qualify(lock, fetch, tmp_path / "out")
    gen, emb = record.models
    assert gen.lock_match and not emb.lock_match
    assert gen.context_length == 262144 and gen.quantization == "Q4_K_M"
    assert gen.license_first_line == "Apache License" and gen.license_spdx_guess == "Apache-2.0"
    assert (tmp_path / "out" / gen.license_file).read_text().strip().startswith("Apache License")
    assert record.runtime_version == record.locked_runtime_version == "0.34.0"
    assert "/api/pull" not in fetch.calls  # never downloads
