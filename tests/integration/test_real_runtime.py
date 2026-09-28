"""Real Ollama verification (research.md R3). Opt-in only: skipped unless
`SCORE_ASSISTANT_REAL_RUNTIME=1` is set, and reported as "not run" (never "passed") when skipped —
see conftest.py's `pytest_collection_modifyitems` and constitution VII."""

from __future__ import annotations

import os

import pytest

from score_docs_assistant.models.ollama import OllamaRuntime

pytestmark = pytest.mark.real_runtime

BASE_URL = "http://127.0.0.1:11434"


def test_real_version_and_tags_parse() -> None:
    runtime = OllamaRuntime(BASE_URL)
    try:
        info = runtime.version()
        assert info.provider == "ollama"
        assert info.version

        models = runtime.list_models()
        for model in models:
            assert model.digest.startswith("sha256:") or len(model.digest) > 0
    finally:
        runtime.close()


def test_real_pull_stream_fields() -> None:
    if os.environ.get("SCORE_ASSISTANT_REAL_PULL") != "1":
        pytest.skip("real model pull disabled (set SCORE_ASSISTANT_REAL_PULL=1 to opt in); not run")
    runtime = OllamaRuntime(BASE_URL)
    try:
        saw_status = False
        for progress in runtime.pull("nomic-embed-text"):
            assert "status" in progress
            saw_status = True
            if progress.get("status") == "success":
                break
        assert saw_status
    finally:
        runtime.close()
