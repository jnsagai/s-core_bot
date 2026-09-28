"""Retrieval evaluation: recall@10, exact-ID suite, latency (FR-019–FR-022, research R8).

Reports built from agent-authored, unreviewed cases carry explicit labels and are development
measurements, never release evidence (constitution VII; release evaluation is F008).
"""

from __future__ import annotations

import hashlib
import platform
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.domain.retrieval import EvidenceResult, SearchRequest
from score_docs_assistant.retrieval.service import SearchService

Category = Literal[
    "onboarding_build", "architecture_interfaces", "process_work_products", "requirements_templates"
]
TOP_K = 10
_FORBID = ConfigDict(extra="forbid", frozen=True)


class Locator(BaseModel):
    model_config = _FORBID

    source_id: str | None = None
    path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    entity_key: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> Locator:
        by_path = self.source_id is not None and self.path is not None
        if by_path == (self.entity_key is not None):
            raise ValueError("a locator has either entity_key, or source_id and path")
        if (self.line_start is None) != (self.line_end is None):
            raise ValueError("line_start and line_end go together")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must be ≥ line_start")
        return self

    def satisfied_by(self, result: EvidenceResult) -> bool:
        if self.entity_key is not None:
            return self.entity_key in result.entity_keys
        if result.source_id != self.source_id or result.path != self.path:
            return False
        if self.line_start is None or result.line_start is None or result.line_end is None:
            return True
        assert self.line_end is not None
        return result.line_start <= self.line_end and self.line_start <= result.line_end


class RetrievalCase(BaseModel):
    model_config = _FORBID

    id: str = Field(min_length=1)
    category: Category
    question: str = Field(min_length=1)
    expected: list[list[Locator]] = Field(min_length=1)
    notes: str = ""

    @model_validator(mode="after")
    def _groups(self) -> RetrievalCase:
        if any(not group for group in self.expected):
            raise ValueError("every evidence group needs at least one locator")
        return self


class CaseFile(BaseModel):
    model_config = _FORBID

    schema_version: Literal[1]
    review_status: str = Field(min_length=1)
    written_against: dict[str, str]
    cases: list[RetrievalCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> CaseFile:
        ids = [c.id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique")
        return self

    @property
    def reviewed(self) -> bool:
        return self.review_status.lower().startswith("reviewed")


def load_case_file(path: Path) -> tuple[CaseFile, str]:
    try:
        raw = path.read_bytes()
        data = yaml.safe_load(raw)
        return CaseFile.model_validate(data), hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        raise ConfigError([(str(path), f"cannot read case file: {exc}")]) from exc
    except yaml.YAMLError as exc:
        raise ConfigError([(str(path), f"invalid YAML: {exc}")]) from exc
    except ValidationError as exc:
        errors = [(f"{path}:{'.'.join(str(p) for p in e['loc'])}", e["msg"]) for e in exc.errors()]
        raise ConfigError(errors) from exc


class CaseResult(BaseModel):
    model_config = _FORBID

    id: str
    category: str
    group_ranks: list[int | None]
    recall_at_10: float


class CategorySummary(BaseModel):
    model_config = _FORBID

    cases: int
    recall_at_10: float


class RetrievalReport(BaseModel):
    model_config = _FORBID

    snapshot_id: str
    generated_at: datetime
    case_file_sha256: str
    review_status: str
    labels: list[str]
    mode: str
    configuration: dict[str, int]
    warnings: list[str]
    cases: list[CaseResult]
    macro_recall_at_10: float
    by_category: dict[str, CategorySummary]


def evaluate_retrieval(
    service: SearchService,
    case_file: CaseFile,
    case_file_sha256: str,
    *,
    snapshot_id: str | None = None,
    force_lexical: bool = False,
) -> RetrievalReport:
    results: list[CaseResult] = []
    modes: set[str] = set()
    resolved_snapshot = ""
    configuration: dict[str, int] = {}
    for case in case_file.cases:
        response = service.search(
            SearchRequest(query=case.question, snapshot_id=snapshot_id, limit=TOP_K),
            force_lexical=force_lexical,
        )
        resolved_snapshot = response.snapshot_id
        modes.add(response.mode)
        configuration = response.retrieval.model_dump()
        ranks: list[int | None] = []
        for group in case.expected:
            hit = next(
                (r.rank for r in response.results if any(loc.satisfied_by(r) for loc in group)),
                None,
            )
            ranks.append(hit)
        found = sum(1 for r in ranks if r is not None)
        results.append(
            CaseResult(
                id=case.id,
                category=case.category,
                group_ranks=ranks,
                recall_at_10=found / len(ranks),
            )
        )
    warnings: list[str] = []
    snapshot_revisions = service.sources(resolved_snapshot).sources
    revisions = {s.source_id: s.revision for s in snapshot_revisions}
    for source_id, revision in case_file.written_against.items():
        if revisions.get(source_id) != revision:
            warnings.append(
                f"case file written against {source_id}@{revision[:12]}, snapshot has "
                f"{(revisions.get(source_id) or 'none')[:12]}"
            )
    by_category: dict[str, CategorySummary] = {}
    for category in sorted({r.category for r in results}):
        members = [r for r in results if r.category == category]
        by_category[category] = CategorySummary(
            cases=len(members), recall_at_10=sum(r.recall_at_10 for r in members) / len(members)
        )
    labels = [] if case_file.reviewed else ["development measurement", "not release evidence"]
    return RetrievalReport(
        snapshot_id=resolved_snapshot,
        generated_at=datetime.now(UTC),
        case_file_sha256=case_file_sha256,
        review_status=case_file.review_status,
        labels=labels,
        mode="+".join(sorted(modes)),
        configuration=configuration,
        warnings=warnings,
        cases=results,
        macro_recall_at_10=sum(r.recall_at_10 for r in results) / len(results),
        by_category=by_category,
    )


class ExactIdFailure(BaseModel):
    model_config = _FORBID

    need_id: str
    expected: str
    got: str | None


class ExactIdReport(BaseModel):
    model_config = _FORBID

    snapshot_id: str
    ids_checked: int
    correct_first: int
    failures: list[ExactIdFailure]
    ambiguous_by_design: list[str]


def exact_id_suite(service: SearchService, *, snapshot_id: str | None = None) -> ExactIdReport:
    """Every distinct need ID in the snapshot → lookup → expected entity first (research R8)."""
    with service.pinned(snapshot_id) as handle:
        index = service.entity_index(handle)
        resolved = handle.snapshot_id
        expected: dict[str, str] = {}
        ambiguous: list[str] = []
        for need_id, entities in sorted(index.groups()):
            expected[need_id] = entities[0].key
            first_order = entities[0].order()
            if len(entities) > 1 and entities[1].order()[:2] == first_order[:2]:
                ambiguous.append(need_id)  # same status and source: duplicates within a source
    failures: list[ExactIdFailure] = []
    for need_id, key in expected.items():
        response = service.lookup(need_id, snapshot_id=resolved)
        got = response.entities[0].key if response.entities else None
        if got != key or response.entities[0].match != "exact":
            failures.append(ExactIdFailure(need_id=need_id, expected=key, got=got))
    return ExactIdReport(
        snapshot_id=resolved,
        ids_checked=len(expected),
        correct_first=len(expected) - len(failures),
        failures=failures,
        ambiguous_by_design=ambiguous,
    )


class ModeLatency(BaseModel):
    model_config = _FORBID

    status: Literal["measured", "not run"]
    queries: int = 0
    p50_ms: float | None = None
    p95_ms: float | None = None
    reason: str = ""


class LatencyReport(BaseModel):
    model_config = _FORBID

    snapshot_id: str
    generated_at: datetime
    warmup: int
    modes: dict[str, ModeLatency]
    embedding_warm: bool
    environment: dict[str, str]
    measured_in: str = "service call (excludes HTTP and process start-up)"


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile (no interpolation), e.g. fraction 0.95 for p95."""
    ordered = sorted(values)
    rank = max(1, -(-int(fraction * 1000) * len(ordered) // 1000))
    return ordered[min(rank, len(ordered)) - 1]


def measure_latency(
    service: SearchService,
    questions: Sequence[str],
    *,
    queries: int = 50,
    warmup: int = 5,
    snapshot_id: str | None = None,
    environment: dict[str, str] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> LatencyReport:
    if not questions:
        raise ConfigError([("questions", "at least one query is needed")])
    resolved = ""
    modes: dict[str, ModeLatency] = {}
    embedding_warm = False
    for mode, force_lexical in (("lexical", True), ("hybrid", False)):
        for i in range(warmup):
            response = service.search(
                SearchRequest(query=questions[i % len(questions)], snapshot_id=snapshot_id),
                force_lexical=force_lexical,
            )
            resolved = response.snapshot_id
        if mode == "hybrid" and response.mode != "hybrid":
            reason = response.degraded.reason if response.degraded else "unknown"
            modes[mode] = ModeLatency(status="not run", reason=reason)
            continue
        embedding_warm = embedding_warm or mode == "hybrid"
        samples: list[float] = []
        for i in range(queries):
            start = clock()
            service.search(
                SearchRequest(query=questions[i % len(questions)], snapshot_id=snapshot_id),
                force_lexical=force_lexical,
            )
            samples.append((clock() - start) * 1000)
        modes[mode] = ModeLatency(
            status="measured",
            queries=len(samples),
            p50_ms=round(percentile(samples, 0.50), 2),
            p95_ms=round(percentile(samples, 0.95), 2),
        )
    return LatencyReport(
        snapshot_id=resolved,
        generated_at=datetime.now(UTC),
        warmup=warmup,
        modes=modes,
        embedding_warm=embedding_warm,
        environment=environment or {"os": platform.platform(), "python": platform.python_version()},
    )
