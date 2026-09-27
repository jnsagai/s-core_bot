"""Domain records for model profiles, runtime identity, and the model acquisition lock."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ModelRole = Literal["generation", "embedding"]
LockCompareStatus = Literal["match", "mismatch", "missing_installed", "not_locked"]


class ProfileModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: ModelRole
    tag: str
    approx_size_bytes: int | None = None
    size_source: str
    license: str | None = None


class ModelProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    models: list[ProfileModel]

    def model_for_role(self, role: ModelRole) -> ProfileModel:
        for model in self.models:
            if model.role == role:
                return model
        raise LookupError(f"profile {self.name!r} has no model for role {role!r}")


class RuntimeInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: Literal["ollama"]
    base_url: str
    version: str


class InstalledModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    tag: str
    digest: str
    size_bytes: int
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    is_remote: bool = False


class ModelLockRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal["ollama"]
    version: str


class ModelLockEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: ModelRole
    tag: str
    digest: str
    size_bytes: int
    acquired_at: datetime


class ModelLock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    profile: str
    runtime: ModelLockRuntime
    models: list[ModelLockEntry] = Field(default_factory=list)

    def entry_for_role(self, role: ModelRole) -> ModelLockEntry | None:
        for entry in self.models:
            if entry.role == role:
                return entry
        return None
