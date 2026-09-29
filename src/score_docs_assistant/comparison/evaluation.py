"""Comparison evaluation (FR-020, SC-005, research R10).

Automated metrics come from the comparison results themselves: difference-type agreement with the
case's expectation, side isolation, citation integrity and forbidden deletion wording. It is a
development measurement until a person reviews the cases; nothing here judges factual quality.
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from score_docs_assistant.comparison.service import ComparisonService
from score_docs_assistant.comparison.validate import DELETION_WORDING
from score_docs_assistant.domain.comparison import (
    ComparisonRequest,
    ComparisonResult,
    DifferenceType,
)
from score_docs_assistant.domain.errors import ConfigError, GenerationError, SearchError

Category = Literal["changed", "unchanged", "missing_coverage", "exact_id", "conflicting"]
MINIMUMS: dict[str, int] = {"missing_coverage": 2, "unchanged": 2, "exact_id": 1}
MIN_CASES = 10
_FORBID = ConfigDict(extra="forbid", frozen=True)


class ComparisonCase(BaseModel):
    model_config = _FORBID

    id: str = Field(min_length=1)
    category: Category
    question: str = Field(min_length=1)
    expected_type: DifferenceType
    acceptable_types: list[DifferenceType] = []
    notes: str = ""


class ComparisonCaseFile(BaseModel):
    model_config = _FORBID

    schema_version: Literal[1]
    review_status: str = Field(min_length=1)
    left_snapshot: str | None = None
    right_snapshot: str | None = None
    written_against: dict[str, str] = {}
    cases: list[ComparisonCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> ComparisonCaseFile:
        ids = [c.id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique")
        return self

    @property
    def reviewed(self) -> bool:
        return self.review_status.lower().startswith("reviewed")

    def composition_problems(self) -> list[str]:
        """Unmet FR-020 minimums for a committed benchmark file (empty when satisfied)."""
        problems = [] if len(self.cases) >= MIN_CASES else [f"fewer than {MIN_CASES} cases"]
        for category, minimum in MINIMUMS.items():
            count = sum(1 for c in self.cases if c.category == category)
            if count < minimum:
                problems.append(f"{category}: {count} < {minimum}")
        return problems


def load_comparison_cases(path: Path) -> tuple[ComparisonCaseFile, str]:
    try:
        raw = path.read_bytes()
        data = ComparisonCaseFile.model_validate(yaml.safe_load(raw))
        return data, hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        raise ConfigError([(str(path), f"cannot read case file: {exc}")]) from exc
    except yaml.YAMLError as exc:
        raise ConfigError([(str(path), f"invalid YAML: {exc}")]) from exc
    except ValidationError as exc:
        raise ConfigError(
            [(f"{path}:{'.'.join(str(p) for p in e['loc'])}", e["msg"]) for e in exc.errors()]
        ) from exc


class ComparisonCaseResult(BaseModel):
    model_config = _FORBID

    id: str
    category: str
    expected_type: str
    observed_types: list[str]
    type_ok: bool
    origin: str | None
    differences: int
    model_differences: int
    isolation_violations: int
    citation_integrity: bool
    deletion_claims: int
    latency_ms: float
    error: str | None = None
    warnings: list[str] = []


class Ratio(BaseModel):
    model_config = _FORBID

    ok: int
    total: int


class ComparisonReport(BaseModel):
    model_config = _FORBID

    left_snapshot_id: str
    right_snapshot_id: str
    model: dict[str, str]
    case_file_sha256: str
    review_status: str
    labels: list[str]
    created_at: datetime
    type_agreement: Ratio
    by_category: dict[str, Ratio]
    isolation_violations: int
    citation_integrity: Ratio
    deletion_claims: int
    deterministic_only: int
    errors: int
    latency_ms: dict[str, float]
    cases: list[ComparisonCaseResult]


def _integrity(result: ComparisonResult) -> tuple[int, bool]:
    left, right = result.snapshots.left_snapshot_id, result.snapshots.right_snapshot_id
    violations = sum(
        1 for c in [*result.left.citations, *result.evidence.left] if c.snapshot_id != left
    ) + sum(1 for c in [*result.right.citations, *result.evidence.right] if c.snapshot_id != right)
    left_ids = {c.evidence_id for c in result.evidence.left}
    right_ids = {c.evidence_id for c in result.evidence.right}
    resolved = all(
        set(d.left_evidence_ids) <= left_ids and set(d.right_evidence_ids) <= right_ids
        for d in result.differences
    )
    return violations, resolved and violations == 0


def score_case(
    case: ComparisonCase, result: ComparisonResult, latency_ms: float
) -> ComparisonCaseResult:
    observed: list[str] = sorted({d.type for d in result.differences})
    accepted = {case.expected_type, *case.acceptable_types}
    violations, integrity = _integrity(result)
    return ComparisonCaseResult(
        id=case.id,
        category=case.category,
        expected_type=case.expected_type,
        observed_types=observed,
        type_ok=bool(accepted & set(observed)),
        origin=result.origin,
        differences=len(result.differences),
        model_differences=sum(1 for d in result.differences if d.origin == "model"),
        isolation_violations=violations,
        citation_integrity=integrity,
        deletion_claims=sum(1 for d in result.differences if DELETION_WORDING.search(d.statement)),
        latency_ms=round(latency_ms, 1),
        warnings=result.warnings,
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


async def evaluate_comparisons(
    service: ComparisonService,
    case_file: ComparisonCaseFile,
    sha: str,
    *,
    left: str,
    right: str,
) -> ComparisonReport:
    identity = await service._answers.identity()  # noqa: SLF001 — fail fast, before any case
    results: list[ComparisonCaseResult] = []
    for case in case_file.cases:
        started = time.monotonic()
        request = ComparisonRequest(
            question=case.question, left_snapshot_id=left, right_snapshot_id=right
        )
        try:
            result = await service.compare(request, request_id=f"eval-{case.id}")
        except GenerationError as exc:
            if exc.code == "GENERATION_UNAVAILABLE":
                raise
            results.append(_failed(case, exc.code, started))
            continue
        except SearchError as exc:
            results.append(_failed(case, exc.code, started))
            continue
        results.append(score_case(case, result, (time.monotonic() - started) * 1000))
    categories: dict[str, Ratio] = {}
    for category in sorted({c.category for c in results}):
        subset = [c for c in results if c.category == category]
        categories[category] = Ratio(ok=sum(c.type_ok for c in subset), total=len(subset))
    latencies = [c.latency_ms for c in results if c.error is None] or [0.0]
    return ComparisonReport(
        left_snapshot_id=left,
        right_snapshot_id=right,
        model={"name": identity.name, "digest": identity.digest},
        case_file_sha256=sha,
        review_status=case_file.review_status,
        labels=[] if case_file.reviewed else ["development measurement", "not release evidence"],
        created_at=datetime.now(UTC),
        type_agreement=Ratio(ok=sum(c.type_ok for c in results), total=len(results)),
        by_category=categories,
        isolation_violations=sum(c.isolation_violations for c in results),
        citation_integrity=Ratio(
            ok=sum(c.citation_integrity for c in results if c.error is None),
            total=sum(1 for c in results if c.error is None),
        ),
        deletion_claims=sum(c.deletion_claims for c in results),
        deterministic_only=sum(1 for c in results if c.origin == "deterministic_only"),
        errors=sum(1 for c in results if c.error is not None),
        latency_ms={
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies),
        },
        cases=results,
    )


def _failed(case: ComparisonCase, code: str, started: float) -> ComparisonCaseResult:
    return ComparisonCaseResult(
        id=case.id,
        category=case.category,
        expected_type=case.expected_type,
        observed_types=[],
        type_ok=False,
        origin=None,
        differences=0,
        model_differences=0,
        isolation_violations=0,
        citation_integrity=False,
        deletion_claims=0,
        latency_ms=round((time.monotonic() - started) * 1000, 1),
        error=code,
    )


def report_path(data_dir: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return data_dir / "reports" / f"comparison-{stamp}.json"
