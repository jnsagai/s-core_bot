"""Answer evaluation: status agreement, citation integrity, evidence overlap, review sheet
(FR-025, research R9).

Automated metrics come from the envelopes themselves. Human-judged metrics (factual support
precision, required-fact coverage) stay "not run" until a person fills in the review sheet, since
valid JSON says nothing about factual quality.
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from score_docs_assistant.answers.service import AnswerService
from score_docs_assistant.domain.answers import AnswerEnvelope, ChatRequest, Citation
from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.retrieval.evaluation import Locator
from score_docs_assistant.retrieval.service import SearchService

ExpectedStatus = Literal[
    "answered", "partial", "insufficient_evidence", "clarification_needed", "safe_handling"
]
SAFE_STATUSES = {"insufficient_evidence", "partial", "clarification_needed"}
_FORBID = ConfigDict(extra="forbid", frozen=True)


class AnswerCase(BaseModel):
    model_config = _FORBID

    id: str = Field(min_length=1)
    category: Literal[
        "onboarding_build",
        "architecture_interfaces",
        "process_work_products",
        "requirements_templates",
        "unanswerable",
        "injection",
    ]
    question: str = Field(min_length=1)
    expected_status: ExpectedStatus
    expected: list[list[Locator]] = []
    notes: str = ""


class AnswerCaseFile(BaseModel):
    model_config = _FORBID

    schema_version: Literal[1]
    review_status: str = Field(min_length=1)
    written_against: dict[str, str]
    snapshot_fixture: Literal["real", "injection"] = "real"
    cases: list[AnswerCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> AnswerCaseFile:
        ids = [c.id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique")
        return self

    @property
    def reviewed(self) -> bool:
        return self.review_status.lower().startswith("reviewed")


def load_answer_cases(path: Path) -> tuple[AnswerCaseFile, str]:
    try:
        raw = path.read_bytes()
        return AnswerCaseFile.model_validate(yaml.safe_load(raw)), hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        raise ConfigError([(str(path), f"cannot read case file: {exc}")]) from exc
    except yaml.YAMLError as exc:
        raise ConfigError([(str(path), f"invalid YAML: {exc}")]) from exc
    except ValidationError as exc:
        raise ConfigError(
            [(f"{path}:{'.'.join(str(p) for p in e['loc'])}", e["msg"]) for e in exc.errors()]
        ) from exc


class AnswerCaseResult(BaseModel):
    model_config = _FORBID

    id: str
    category: str
    status: str
    expected_status: str
    status_ok: bool
    origin: str
    citations: int
    citation_integrity: bool
    evidence_overlap: float | None
    documented_claims: int
    latency_ms: float
    warnings: list[str]


class RatioSummary(BaseModel):
    model_config = _FORBID

    ok: int
    total: int


class HumanReview(BaseModel):
    model_config = _FORBID

    support_precision: str
    required_fact_coverage: str


class AnswerReport(BaseModel):
    model_config = _FORBID

    snapshot_id: str
    generated_at: datetime
    model: dict[str, str | None]
    case_file_sha256: str
    review_status: str
    labels: list[str]
    cases: list[AnswerCaseResult]
    by_category: dict[str, RatioSummary]
    status_agreement: RatioSummary
    safe_handling: RatioSummary
    citation_integrity: RatioSummary
    human_review: HumanReview


def citation_intact(search: SearchService, snapshot_id: str, citation: Citation) -> bool:
    """The citation's chunk exists in the snapshot and its excerpt is the stored text."""
    with search.pinned(snapshot_id) as handle:
        row = (
            handle.corpus()
            .execute(
                "SELECT text, source_id, path FROM chunks WHERE chunk_id = ?", (citation.chunk_id,)
            )
            .fetchone()
        )
    if row is None:
        return False
    text, source_id, path = row
    return (
        str(text).startswith(citation.excerpt.rstrip())
        and source_id == citation.source_id
        and path == citation.path
    )


def _entity_keys(search: SearchService, snapshot_id: str, chunk_id: str) -> list[str]:
    import json

    with search.pinned(snapshot_id) as handle:
        row = (
            handle.corpus()
            .execute("SELECT entity_keys_json FROM chunks WHERE chunk_id = ?", (chunk_id,))
            .fetchone()
        )
    return list(json.loads(row[0])) if row else []


def _satisfies(locator: Locator, citation: Citation, entity_keys: list[str]) -> bool:
    if locator.entity_key is not None:
        return locator.entity_key in entity_keys
    if citation.source_id != locator.source_id or citation.path != locator.path:
        return False
    if locator.line_start is None or citation.line_start is None or citation.line_end is None:
        return True
    assert locator.line_end is not None
    return citation.line_start <= locator.line_end and locator.line_start <= citation.line_end


def _status_ok(expected: str, status: str) -> bool:
    return status in SAFE_STATUSES if expected == "safe_handling" else status == expected


async def evaluate_answers(
    service: AnswerService,
    search: SearchService,
    case_file: AnswerCaseFile,
    case_file_sha256: str,
    *,
    snapshot_id: str | None = None,
) -> tuple[AnswerReport, dict[str, object]]:
    results: list[AnswerCaseResult] = []
    sheet_cases: list[dict[str, object]] = []
    resolved = ""
    model: dict[str, str | None] = {}
    for case in case_file.cases:
        started = time.monotonic()
        envelope: AnswerEnvelope = await service.answer(
            ChatRequest(question=case.question, snapshot_id=snapshot_id), request_id=case.id
        )
        latency = (time.monotonic() - started) * 1000
        resolved = envelope.snapshot_id
        if envelope.model is not None:
            model = envelope.model.model_dump()
        intact = all(citation_intact(search, resolved, c) for c in envelope.citations)
        overlap: float | None = None
        if case.expected:
            keys = {
                c.chunk_id: _entity_keys(search, resolved, c.chunk_id) for c in envelope.citations
            }
            satisfied = sum(
                1
                for group in case.expected
                if any(
                    _satisfies(loc, c, keys[c.chunk_id])
                    for loc in group
                    for c in envelope.citations
                )
            )
            overlap = satisfied / len(case.expected)
        results.append(
            AnswerCaseResult(
                id=case.id,
                category=case.category,
                status=envelope.status,
                expected_status=case.expected_status,
                status_ok=_status_ok(case.expected_status, envelope.status),
                origin=envelope.origin,
                citations=len(envelope.citations),
                citation_integrity=intact,
                evidence_overlap=overlap,
                documented_claims=sum(1 for c in envelope.claims if c.kind == "documented"),
                latency_ms=round(latency, 1),
                warnings=list(envelope.warnings),
            )
        )
        by_id = {c.evidence_id: c for c in envelope.citations}
        sheet_cases.append(
            {
                "id": case.id,
                "question": case.question,
                "status": envelope.status,
                "claims": [
                    {
                        "text": claim.text,
                        "kind": claim.kind,
                        "citations": [
                            {
                                "path": by_id[e].path,
                                "lines": [by_id[e].line_start, by_id[e].line_end],
                                "excerpt": by_id[e].excerpt,
                            }
                            for e in claim.evidence_ids
                        ],
                        "supported": None,
                        "reviewer": None,
                    }
                    for claim in envelope.claims
                    if claim.kind != "limitation"
                ],
            }
        )
    by_category: dict[str, RatioSummary] = {}
    for category in sorted({r.category for r in results}):
        members = [r for r in results if r.category == category]
        by_category[category] = RatioSummary(
            ok=sum(1 for r in members if r.status_ok), total=len(members)
        )
    unsafe_expected = [r for r in results if r.expected_status == "safe_handling"]
    report = AnswerReport(
        snapshot_id=resolved,
        generated_at=datetime.now(UTC),
        model=model,
        case_file_sha256=case_file_sha256,
        review_status=case_file.review_status,
        labels=[] if case_file.reviewed else ["development measurement", "not release evidence"],
        cases=results,
        by_category=by_category,
        status_agreement=RatioSummary(ok=sum(r.status_ok for r in results), total=len(results)),
        safe_handling=RatioSummary(
            ok=sum(r.status_ok for r in unsafe_expected), total=len(unsafe_expected)
        ),
        citation_integrity=RatioSummary(
            ok=sum(r.citation_integrity for r in results), total=len(results)
        ),
        human_review=HumanReview(
            support_precision="not run (review sheet not filled)",
            required_fact_coverage="not run (no reviewed required facts; F008)",
        ),
    )
    sheet: dict[str, object] = {
        "schema_version": 1,
        "snapshot_id": resolved,
        "case_file_sha256": case_file_sha256,
        "instructions": (
            "For each claim set supported to true or false after reading its cited excerpts, "
            "and reviewer to your role and date. Then pass this file with --review."
        ),
        "cases": sheet_cases,
    }
    return report, sheet


def apply_review(report: AnswerReport, sheet_path: Path) -> AnswerReport:
    """Compute factual support precision from a filled review sheet."""
    try:
        sheet = yaml.safe_load(sheet_path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError([(str(sheet_path), f"cannot read review sheet: {exc}")]) from exc
    if not isinstance(sheet, dict) or sheet.get("case_file_sha256") != report.case_file_sha256:
        raise ConfigError([(str(sheet_path), "review sheet does not belong to this case file")])
    judged = [
        claim["supported"]
        for case in sheet.get("cases", [])
        for claim in case.get("claims", [])
        if isinstance(claim.get("supported"), bool) and claim.get("reviewer")
    ]
    if not judged:
        return report
    precision = sum(1 for s in judged if s) / len(judged)
    return report.model_copy(
        update={
            "human_review": HumanReview(
                support_precision=f"{precision:.1%} of {len(judged)} human-reviewed claims",
                required_fact_coverage=report.human_review.required_fact_coverage,
            )
        }
    )
