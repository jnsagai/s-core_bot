"""Refresh records (specs/015-scheduled-refresh/data-model.md). No FastAPI or Ollama types."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Outcome = Literal["up-to-date", "activated", "held", "failed", "busy"]
EXIT_CODES: dict[str, int] = {"up-to-date": 0, "activated": 0, "failed": 1, "held": 3, "busy": 4}

_FORBID = ConfigDict(extra="forbid")


class SourceCheck(BaseModel):
    model_config = _FORBID

    source_id: str
    kind: Literal["git", "needs-export"]
    status: Literal["unchanged", "changed", "unknown"]
    locked: str | None = None
    upstream: str | None = None
    detail: str = ""


class GateCheck(BaseModel):
    model_config = _FORBID

    id: Literal["integrity", "exact_ids", "coverage_drop", "semantic", "required_sources"]
    status: Literal["pass", "fail"]
    detail: str


class RevisionChange(BaseModel):
    model_config = _FORBID

    source_id: str
    before: str | None
    after: str | None


class ExportValidator(BaseModel):
    model_config = _FORBID

    url: str
    etag: str | None = None
    last_modified: str | None = None


class RefreshRun(BaseModel):
    model_config = _FORBID

    started_at: datetime
    finished_at: datetime
    outcome: Outcome
    reason: str
    active_before: str | None = None
    active_after: str | None = None
    candidate: str | None = None
    candidate_semantic: Literal["present", "absent"] | None = None
    checks: list[SourceCheck] = Field(default_factory=list)
    synced: bool = False
    lock_changed: bool = False
    revision_changes: list[RevisionChange] = Field(default_factory=list)
    gate: list[GateCheck] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.outcome]


class RefreshState(BaseModel):
    model_config = _FORBID

    schema_version: Literal[1] = 1
    last_run: RefreshRun | None = None
    last_success_at: datetime | None = None
    exports: dict[str, ExportValidator] = Field(default_factory=dict)
