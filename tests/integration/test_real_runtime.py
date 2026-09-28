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


# --- F003: real embedding provider (specs/003-snapshot-index/research.md R1) -----------------


def _embedding_provider():  # type: ignore[no-untyped-def]
    from score_docs_assistant.domain.snapshots import ChunkerConfig
    from score_docs_assistant.models.ollama_embed import OllamaEmbeddingProvider

    return OllamaEmbeddingProvider(BASE_URL, "nomic-embed-text", config=ChunkerConfig())


def test_real_embedding_identity_matches_model_lock() -> None:
    from pathlib import Path

    from score_docs_assistant.models.lock import read_lock

    provider = _embedding_provider()
    try:
        identity = provider.identity()
        assert identity.dimension == 768
        assert provider.context_tokens() == 2048
        lock = read_lock(Path(__file__).parent.parent.parent / "data" / "model-lock.json")
        if lock is not None and (entry := lock.entry_for_role("embedding")) is not None:
            assert identity.model_digest == entry.digest.removeprefix("sha256:")
    finally:
        provider.close()


def test_real_over_bound_input_is_refused_not_truncated() -> None:
    from score_docs_assistant.domain.errors import SnapshotError

    provider = _embedding_provider()
    try:
        with pytest.raises(SnapshotError) as exc_info:
            provider.embed(["word " * 3000])
        assert exc_info.value.code == "EMBEDDING_INPUT_TOO_LONG"
        [vector] = provider.embed(["search_document: hello"])
        assert len(vector) == 768
    finally:
        provider.close()


def test_real_fixture_build_validates(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from score_docs_assistant.storage.build import BuildService
    from tests.helpers.build import app_config
    from tests.helpers.snapshot_env import PROFILES, make_env, write_model_lock

    env = make_env(tmp_path)
    provider = _embedding_provider()
    try:
        identity = provider.identity()
        write_model_lock(env.data, identity.model_digest)
        result = BuildService(
            config=app_config(env.data), profiles_dir=PROFILES, provider=provider
        ).run(env.lock_path)
        assert result.state == "validated" and result.semantic == "present"
    finally:
        provider.close()
