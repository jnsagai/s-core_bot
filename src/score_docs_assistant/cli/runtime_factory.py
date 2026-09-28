"""Builds the configured `ModelRuntime`. A single seam so tests can substitute a fake transport
without the CLI commands knowing about test fixtures."""

from __future__ import annotations

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.models.ollama import OllamaRuntime
from score_docs_assistant.models.runtime import EmbeddingProvider, GenerationProvider, ModelRuntime


def build_runtime(config: AppConfig) -> ModelRuntime:
    return OllamaRuntime(
        config.runtime.base_url,
        connect_timeout=config.diagnostics.runtime_connect_timeout_seconds,
        read_timeout=config.diagnostics.runtime_read_timeout_seconds,
    )


def build_embedding_provider(config: AppConfig) -> EmbeddingProvider:
    """Seam for tests: the loopback Ollama embedding provider (F003)."""
    from score_docs_assistant.models.ollama_embed import OllamaEmbeddingProvider
    from score_docs_assistant.storage.build import chunker_config

    return OllamaEmbeddingProvider(
        config.runtime.base_url,
        config.runtime.embedding_model,
        config=chunker_config(config),
        timeout_seconds=config.index.embedding_timeout_seconds,
        connect_timeout_seconds=config.diagnostics.runtime_connect_timeout_seconds,
    )


def build_generation_provider(config: AppConfig) -> GenerationProvider:
    """Seam for tests: the loopback Ollama generation provider (F005)."""
    from score_docs_assistant.models.ollama_chat import OllamaGenerationProvider

    return OllamaGenerationProvider(
        config.runtime.base_url,
        config.runtime.generation_model,
        timeout_seconds=float(config.limits.request_deadline_seconds),
        connect_timeout_seconds=config.diagnostics.runtime_connect_timeout_seconds,
    )
