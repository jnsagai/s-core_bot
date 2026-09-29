"""HTTP response and error-envelope schemas (contracts/http-api.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    request_id: str
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: ErrorDetail


class LivenessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["alive"] = "alive"


class CapabilityStateOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    available: bool
    reasons: list[str]


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    ready: bool
    capabilities: dict[str, CapabilityStateOut]


class AppInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    version: str


class LimitsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_characters: int
    history_characters: int
    active_generations: int
    queued_generations: int
    request_deadline_seconds: int
    comparison_deadline_seconds: int


class ModelsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    generation: str
    embedding: str


class CapabilitiesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    app: AppInfo
    profile: Literal["local"] = "local"
    runs_locally: bool = True
    modes: dict[str, CapabilityStateOut]
    limits: LimitsOut
    models: ModelsOut
    response_languages: list[str] = Field(default_factory=lambda: ["en"])
