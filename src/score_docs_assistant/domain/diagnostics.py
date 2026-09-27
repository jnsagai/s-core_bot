"""Diagnostic report types produced by `score-assistant doctor`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckStatus = Literal["ok", "warning", "failure", "info", "skipped"]

DetailValue = str | int | float | bool | None


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: CheckStatus
    code: str
    message: str
    next_action: str | None = None
    details: dict[str, DetailValue] = Field(default_factory=dict)


class DiagnosticReport(BaseModel):
    """Invariant: exit_code == 1 iff any check has status "failure", except a config-error
    report, which contains only the config check and always has exit_code == 2."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    app_version: str
    generated_at: datetime
    checks: list[CheckResult]
    exit_code: Literal[0, 1, 2]

    @classmethod
    def from_checks(cls, app_version: str, checks: list[CheckResult]) -> DiagnosticReport:
        exit_code: Literal[0, 1] = 1 if any(c.status == "failure" for c in checks) else 0
        return cls(
            app_version=app_version,
            generated_at=datetime.now(UTC),
            checks=checks,
            exit_code=exit_code,
        )

    @classmethod
    def from_config_error(cls, app_version: str, check: CheckResult) -> DiagnosticReport:
        return cls(
            app_version=app_version,
            generated_at=datetime.now(UTC),
            checks=[check],
            exit_code=2,
        )
