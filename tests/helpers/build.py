"""Run `BuildService` against a `SnapshotEnv` with the fake (mocked) embedding provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.storage.build import BuildResult, BuildService, StageHook
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.snapshot_env import PROFILES, SnapshotEnv, write_model_lock

PLENTY = 10**15


def app_config(data: Path, **index: Any) -> AppConfig:
    return AppConfig(data_dir=data, index=index or {})  # type: ignore[arg-type]


def build(
    env: SnapshotEnv,
    provider: FakeEmbeddingProvider | None = None,
    *,
    lexical_only: bool = False,
    stage_hook: StageHook | None = None,
    free: int = PLENTY,
    write_lock: bool = True,
    **service: Any,
) -> BuildResult:
    provider = provider if provider is not None else FakeEmbeddingProvider()
    if write_lock:
        write_model_lock(env.data, provider.digest)
    return BuildService(
        config=app_config(env.data),
        profiles_dir=PROFILES,
        provider=provider,
        lexical_only=lexical_only,
        stage_hook=stage_hook,
        free_bytes=lambda _path: free,
        **service,
    ).run(env.lock_path)
