"""AppConfig schema: every key, default, and constraint from contracts/config.md.

All models use `extra="forbid"` so unknown keys at any level are validation errors, and every
constraint is expressed as a pydantic validator so a single `AppConfig(**data)` call collects every
violation (via `ValidationError.errors()`) rather than failing on the first one.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ORIGIN_RE = re.compile(r"^https?://[^/@]+$")


def is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_origin(origin: str) -> None:
    if "@" in origin:
        raise ValueError(f"{origin!r}: must not contain userinfo")
    if not _ORIGIN_RE.match(origin):
        raise ValueError(f"{origin!r}: must be http(s)://host[:port] with no path or wildcard")


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8080", "http://localhost:8080"]
    )

    @field_validator("host")
    @classmethod
    def _host_is_loopback(cls, v: str) -> str:
        if not is_loopback_host(v):
            raise ValueError("must be a loopback address (127.0.0.0/8, ::1, or localhost)")
        return v

    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("must be non-empty")
        return v

    @field_validator("allowed_origins")
    @classmethod
    def _allowed_origins_valid(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("must be non-empty")
        for origin in v:
            _validate_origin(origin)
        return v


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama"] = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    cloud_fallback: Literal[False] = False
    model_profile: str = "local-small"
    generation_model: str = Field(default="qwen3:4b-instruct", min_length=1)
    embedding_model: str = Field(default="nomic-embed-text", min_length=1)
    models_dir: Path | None = None
    context_tokens: int = Field(default=8192, ge=1024, le=131072)
    output_tokens: int = Field(default=900, ge=1)

    @field_validator("base_url")
    @classmethod
    def _base_url_local_http(cls, v: str) -> str:
        parts = urlsplit(v)
        if parts.scheme != "http":
            raise ValueError("scheme must be http")
        if "@" in parts.netloc:
            raise ValueError("must not contain userinfo")
        if parts.path not in ("", "/"):
            raise ValueError("must not contain a path")
        host = parts.hostname
        if host is None or not is_loopback_host(host):
            raise ValueError("host must be a loopback address")
        return v

    @model_validator(mode="after")
    def _output_within_half_context(self) -> RuntimeConfig:
        if self.output_tokens > self.context_tokens // 2:
            raise ValueError("output_tokens must be at most context_tokens / 2")
        return self


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lexical_candidates: int = Field(default=30, ge=1)
    semantic_candidates: int = Field(default=30, ge=1)
    evidence_chunks: int = Field(default=8, ge=1)
    fusion_constant: int = Field(default=60, ge=1)
    max_limit: int = Field(default=20, ge=1, le=100)
    max_per_document: int = Field(default=3, ge=1)
    excerpt_characters: int = Field(default=1200, ge=200, le=10_000)
    max_concurrent_searches: int = Field(default=4, ge=1, le=64)
    semantic_status_ttl_seconds: int = Field(default=30, ge=0, le=3600)

    @model_validator(mode="after")
    def _limit_covers_default(self) -> RetrievalConfig:
        if self.max_limit < self.evidence_chunks:
            raise ValueError("max_limit must be at least evidence_chunks")
        return self


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_characters: int = Field(default=4000, ge=1, le=100_000)
    history_characters: int = Field(default=12_000, ge=0, le=1_000_000)
    active_generations: Literal[1] = 1
    queued_generations: int = Field(default=4, ge=0, le=100)
    request_deadline_seconds: int = Field(default=120, ge=1, le=3600)


class PrivacyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persist_chats: Literal[False] = False
    log_message_bodies: bool = False
    telemetry: Literal[False] = False


class DiagnosticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_connect_timeout_seconds: float = Field(default=1.0, ge=0.1, le=10)
    runtime_read_timeout_seconds: float = Field(default=3.0, ge=0.1, le=30)
    readiness_cache_seconds: float = Field(default=2.0, ge=0, le=60)
    disk_margin_bytes: int = Field(default=2_147_483_648, ge=0)


class IndexConfig(BaseModel):
    """Chunking, embedding and retention settings (specs/003-snapshot-index/data-model.md)."""

    model_config = ConfigDict(extra="forbid")

    chunk_min_tokens: int = Field(default=350, ge=100)
    chunk_max_tokens: int = Field(default=700, ge=100)
    chunk_overlap_tokens: int = Field(default=75, ge=50, le=100)
    embedding_max_input_tokens: int = Field(default=1800, ge=300)
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_timeout_seconds: int = Field(default=120, ge=1, le=600)
    retention_count: int = Field(default=2, ge=2)

    @model_validator(mode="after")
    def _budgets_consistent(self) -> IndexConfig:
        if self.chunk_min_tokens > self.chunk_max_tokens:
            raise ValueError("chunk_min_tokens must not exceed chunk_max_tokens")
        # Leave room for the synthetic embedding prefix (research R3.10).
        if self.chunk_max_tokens > self.embedding_max_input_tokens - 200:
            raise ValueError("chunk_max_tokens must be at most embedding_max_input_tokens - 200")
        return self


class BundleConfig(BaseModel):
    """Bundle import caps (spec clarification Q3)."""

    model_config = ConfigDict(extra="forbid")

    max_total_bytes: int = Field(default=2 * 1024**3, ge=1)
    max_entries: int = Field(default=10_000, ge=1)
    disk_margin_bytes: int = Field(default=1024**3, ge=0)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    profile: Literal["local"] = "local"
    server: ServerConfig = Field(default_factory=ServerConfig)
    data_dir: Path = Path("data")
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    diagnostics: DiagnosticsConfig = Field(default_factory=DiagnosticsConfig)
    index: IndexConfig = Field(default_factory=IndexConfig)
    bundles: BundleConfig = Field(default_factory=BundleConfig)
