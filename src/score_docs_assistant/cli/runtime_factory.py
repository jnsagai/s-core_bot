"""Builds the configured `ModelRuntime`. A single seam so tests can substitute a fake transport
without the CLI commands knowing about test fixtures."""

from __future__ import annotations

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.models.ollama import OllamaRuntime
from score_docs_assistant.models.runtime import ModelRuntime


def build_runtime(config: AppConfig) -> ModelRuntime:
    return OllamaRuntime(
        config.runtime.base_url,
        connect_timeout=config.diagnostics.runtime_connect_timeout_seconds,
        read_timeout=config.diagnostics.runtime_read_timeout_seconds,
    )
