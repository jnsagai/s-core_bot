"""Capability readiness types shared by the readiness service and the HTTP API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Capability(StrEnum):
    SEARCH = "search"
    CHAT = "chat"
    COMPARE = "compare"


class ReasonCode(StrEnum):
    CORPUS_MISSING = "corpus_missing"
    CORPUS_INCOMPATIBLE = "corpus_incompatible"
    RUNTIME_UNREACHABLE = "runtime_unreachable"
    RUNTIME_INCOMPATIBLE = "runtime_incompatible"
    GENERATION_MODEL_MISSING = "generation_model_missing"
    EMBEDDING_MODEL_MISSING = "embedding_model_missing"
    MODEL_IDENTITY_MISMATCH = "model_identity_mismatch"
    NOT_IMPLEMENTED = "not_implemented"


class CapabilityState(BaseModel):
    model_config = ConfigDict(frozen=True)

    available: bool
    reasons: list[ReasonCode] = Field(default_factory=list)


class Readiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    capabilities: dict[Capability, CapabilityState]
    checked_at: datetime

    @property
    def ready(self) -> bool:
        return self.capabilities[Capability.SEARCH].available
