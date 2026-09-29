"""Suite harness: retrieval + answers per case, master §13.3 metrics (F008 FR-007–FR-009, R3).

Every value carries its numerator and denominator. Reports are labelled "development measurement"
unless the file is the frozen held-out split and every case is human-reviewed. While the suite
runs, log records are captured and scanned for question text (privacy evidence, FR-012).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from score_docs_assistant.answers.evaluation import _entity_keys, _satisfies, citation_intact
from score_docs_assistant.answers.service import AnswerService
from score_docs_assistant.domain.answers import AnswerEnvelope, ChatRequest
from score_docs_assistant.domain.retrieval import SearchRequest
from score_docs_assistant.qualification.suite import SuiteCase, SuiteFile
from score_docs_assistant.retrieval.service import SearchService

SAFE_STATUSES = {"insufficient_evidence", "partial", "clarification_needed"}
ABSTAINED = {"insufficient_evidence", "clarification_needed"}
TOP_K = 10
_FORBID = ConfigDict(extra="forbid", frozen=True)


class Metric(BaseModel):
    model_config = _FORBID

    value: float | None
    numerator: float
    denominator: int


class SuiteCaseResult(BaseModel):
    model_config = _FORBID

    id: str
    category: str
    tags: list[str]
    expected_status: str
    status: str
    status_ok: bool
    answerable: bool
    safe_ok: bool | None
    false_abstention: bool | None
    recall_at_10: float | None
    citation_integrity: bool
    forbidden_hits: list[str]
    evidence_overlap: float | None
    origin: str
    latency_ms: float
    claims: int
    warnings: list[str]


class Privacy(BaseModel):
    model_config = _FORBID

    log_records_scanned: int
    question_text_found: int


class SuiteRunReport(BaseModel):
    model_config = _FORBID

    split: str
    run: int
    snapshot_id: str
    model: dict[str, str | None]
    case_file_sha256: str
    freeze: str
    labels: list[str]
    metrics: dict[str, Metric]
    by_category: dict[str, dict[str, Metric]]
    cases: list[SuiteCaseResult]
    privacy: Privacy
    created_at: datetime


class CombinedReport(BaseModel):
    model_config = _FORBID

    split: str
    snapshot_id: str
    model: dict[str, str | None]
    case_file_sha256: str
    freeze: str
    labels: list[str]
    runs: list[dict[str, Metric]]
    run_files: list[str]
    spread: dict[str, dict[str, float | None]]
    created_at: datetime


@contextmanager
def capture_logs() -> Iterator[list[str]]:
    """Collect every formatted log record emitted while the suite runs."""
    records: list[str] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(self.format(record) + " " + repr(getattr(record, "__dict__", {})))

    handler = _Collector(level=logging.DEBUG)
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


_NEGATION = re.compile(
    r"\b(not|no|never|none|neither|nor|without|cannot|can't|doesn't|don't|isn't|aren't|"
    r"wasn't|weren't|won't|nothing)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+")


def asserts(pattern: str, text: str) -> bool:
    """True when a sentence states the forbidden content; a negation before it is a denial.

    A real run showed correct denials ("the platform is not certified …") matching plain
    substrings. The check stays a proxy: human review decides (docs/quality/review-rubric.md).
    """
    for sentence in _SENTENCE.split(text):
        if pattern.startswith("re:"):
            match = re.search(pattern[3:], sentence, re.IGNORECASE)
            start = match.start() if match else -1
        else:
            start = sentence.lower().find(pattern.lower())
        if start >= 0 and not _NEGATION.search(sentence[:start]):
            return True
    return False


def forbidden_hits(case: SuiteCase, envelope: AnswerEnvelope) -> list[str]:
    text = "\n".join(c.text for c in envelope.claims)
    return [pattern for pattern in case.forbidden if asserts(pattern, text)]


def _ratio(hits: list[bool]) -> Metric:
    return Metric(
        value=(sum(hits) / len(hits)) if hits else None,
        numerator=sum(hits),
        denominator=len(hits),
    )


def _mean(values: list[float]) -> Metric:
    return Metric(
        value=(sum(values) / len(values)) if values else None,
        numerator=round(sum(values), 4),
        denominator=len(values),
    )


def metrics_for(results: list[SuiteCaseResult]) -> dict[str, Metric]:
    return {
        "recall_at_10": _mean([r.recall_at_10 for r in results if r.recall_at_10 is not None]),
        "status_agreement": _ratio([r.status_ok for r in results]),
        "safe_handling": _ratio([bool(r.safe_ok) for r in results if r.safe_ok is not None]),
        "false_abstention": _ratio(
            [bool(r.false_abstention) for r in results if r.false_abstention is not None]
        ),
        "citation_integrity": _ratio([r.citation_integrity for r in results]),
        "forbidden_assertions": Metric(
            value=float(sum(len(r.forbidden_hits) for r in results)),
            numerator=sum(1 for r in results if r.forbidden_hits),
            denominator=len(results),
        ),
        "evidence_overlap": _mean(
            [r.evidence_overlap for r in results if r.evidence_overlap is not None]
        ),
        "latency_ms_mean": _mean([r.latency_ms for r in results]),
    }


async def run_suite(
    *,
    search: SearchService,
    answers: AnswerService,
    suite: SuiteFile,
    sha: str,
    freeze: str,
    run: int = 1,
    snapshot_id: str | None = None,
) -> tuple[SuiteRunReport, list[tuple[SuiteCase, AnswerEnvelope]]]:
    results: list[SuiteCaseResult] = []
    envelopes: list[tuple[SuiteCase, AnswerEnvelope]] = []
    model: dict[str, str | None] = {}
    resolved = snapshot_id or ""
    with capture_logs() as records:
        for case in suite.cases:
            recall: float | None = None
            if case.answerable and case.evidence:
                response = search.search(
                    SearchRequest(query=case.question, snapshot_id=snapshot_id, limit=TOP_K)
                )
                found = sum(
                    1
                    for group in case.evidence
                    if any(loc.satisfied_by(r) for r in response.results for loc in group)
                )
                recall = found / len(case.evidence)
            started = time.monotonic()
            envelope = await answers.answer(
                ChatRequest(question=case.question, snapshot_id=snapshot_id),
                request_id=f"suite-{case.id}",
            )
            latency = (time.monotonic() - started) * 1000
            resolved = envelope.snapshot_id
            if envelope.model is not None:
                model = envelope.model.model_dump()
            overlap: float | None = None
            if case.evidence:
                keys = {
                    c.chunk_id: _entity_keys(search, resolved, c.chunk_id)
                    for c in envelope.citations
                }
                satisfied = sum(
                    1
                    for group in case.evidence
                    if any(
                        _satisfies(loc, c, keys[c.chunk_id])
                        for loc in group
                        for c in envelope.citations
                    )
                )
                overlap = satisfied / len(case.evidence)
            status = envelope.status
            expected = case.expected_status
            status_ok = (
                status in SAFE_STATUSES if expected == "safe_handling" else status == expected
            )
            results.append(
                SuiteCaseResult(
                    id=case.id,
                    category=case.category,
                    tags=case.tags,
                    expected_status=expected,
                    status=status,
                    status_ok=status_ok,
                    answerable=case.answerable,
                    safe_ok=None if case.answerable else status in SAFE_STATUSES,
                    false_abstention=status in ABSTAINED if case.answerable else None,
                    recall_at_10=recall,
                    citation_integrity=all(
                        citation_intact(search, resolved, c) for c in envelope.citations
                    ),
                    forbidden_hits=forbidden_hits(case, envelope),
                    evidence_overlap=overlap,
                    origin=envelope.origin,
                    latency_ms=round(latency, 1),
                    claims=len(envelope.claims),
                    warnings=list(envelope.warnings),
                )
            )
            envelopes.append((case, envelope))
    leaks = sum(1 for case in suite.cases if any(case.question in record for record in records))
    by_category = {
        category: metrics_for([r for r in results if r.category == category])
        for category in sorted({r.category for r in results})
    }
    labelled = suite.split == "heldout" and suite.human_reviewed
    return (
        SuiteRunReport(
            split=suite.split,
            run=run,
            snapshot_id=resolved,
            model=model,
            case_file_sha256=sha,
            freeze=freeze,
            labels=[] if labelled else ["development measurement", "not release evidence"],
            metrics=metrics_for(results),
            by_category=by_category,
            cases=results,
            privacy=Privacy(log_records_scanned=len(records), question_text_found=leaks),
            created_at=datetime.now(UTC),
        ),
        envelopes,
    )


def combine_runs(reports: list[SuiteRunReport], files: list[str]) -> CombinedReport:
    first = reports[0]
    names = list(first.metrics)
    spread: dict[str, dict[str, float | None]] = {}
    for name in names:
        values = [v for r in reports if (v := r.metrics[name].value) is not None]
        spread[name] = {
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "range": (max(values) - min(values)) if values else None,
        }
    return CombinedReport(
        split=first.split,
        snapshot_id=first.snapshot_id,
        model=first.model,
        case_file_sha256=first.case_file_sha256,
        freeze=first.freeze,
        labels=first.labels,
        runs=[r.metrics for r in reports],
        run_files=files,
        spread=spread,
        created_at=datetime.now(UTC),
    )


def claim_id(case_id: str, text: str) -> str:
    return hashlib.sha256(f"{case_id}\n{text}".encode()).hexdigest()[:16]


def report_digest(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


def as_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2) + "\n"
