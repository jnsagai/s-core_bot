"""Human review sheets and their import (F008 FR-004–FR-006, research R4).

The sheet is generated for a person to fill in; importing it is the only way the human-judged
metrics stop being "blocked". A sheet without a reviewer and a date is rejected, and nothing here
can fill in judgements.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from score_docs_assistant.domain.answers import AnswerEnvelope
from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.qualification.harness import (
    Metric,
    SuiteRunReport,
    claim_id,
    forbidden_hits,
)
from score_docs_assistant.qualification.suite import SuiteCase

ClaimJudgement = Literal["supported", "partially_supported", "unsupported", "not_factual"]
FactJudgement = Literal["covered", "partly", "missing", "wrong"]
CLAIM_VALUES = {"supported", "partially_supported", "unsupported", "not_factual"}
FACT_VALUES = {"covered": 1.0, "partly": 0.5, "missing": 0.0, "wrong": 0.0}
INSTRUCTIONS = (
    "Judge every claim against ITS cited excerpts only, following docs/quality/review-rubric.md: "
    "supported | partially_supported | unsupported | not_factual. A citation alone does not make a "
    "claim supported. For each required fact of an answerable case: covered | partly | missing | "
    "wrong. Fill reviewer and reviewed_on (YYYY-MM-DD), then run `eval review import`."
)
_FORBID = ConfigDict(extra="forbid", frozen=True)


def build_sheet(
    report_file: str, report_sha256: str, pairs: list[tuple[SuiteCase, AnswerEnvelope]]
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for case, envelope in pairs:
        by_id = {c.evidence_id: c for c in envelope.citations}
        cases.append(
            {
                "id": case.id,
                "category": case.category,
                "question": case.question,
                "expected_status": case.expected_status,
                "status": envelope.status,
                "forbidden_hits_automated": forbidden_hits(case, envelope),
                "facts": [
                    {
                        "fact": f.fact,
                        "variants": f.variants,
                        "required": f.required,
                        "judgement": None,
                    }
                    for f in case.expected_facts
                ]
                if case.answerable
                else [],
                "claims": [
                    {
                        "claim_id": claim_id(case.id, claim.text),
                        "kind": claim.kind,
                        "text": claim.text,
                        "citations": [
                            {
                                "evidence_id": e,
                                "path": by_id[e].path,
                                "lines": [by_id[e].line_start, by_id[e].line_end],
                                "excerpt": by_id[e].excerpt,
                            }
                            for e in claim.evidence_ids
                            if e in by_id
                        ],
                        "judgement": None,
                        "note": "",
                    }
                    for claim in envelope.claims
                    if claim.kind != "limitation"
                ],
            }
        )
    return {
        "schema_version": 1,
        "run_reference": {"file": report_file, "sha256": report_sha256},
        "reviewer": None,
        "reviewed_on": None,
        "instructions": INSTRUCTIONS,
        "cases": cases,
    }


class HumanReview(BaseModel):
    model_config = _FORBID

    reviewer: str
    reviewed_on: str
    run_reference: dict[str, str]
    split: str
    run: int
    snapshot_id: str
    model: dict[str, str | None]
    freeze: str
    support_precision: Metric
    support_precision_by_category: dict[str, Metric]
    required_fact_coverage: Metric
    required_fact_coverage_by_category: dict[str, Metric]
    unreviewed_claims: int
    unreviewed_facts: int
    # "per_item": every judgement written by the reviewer. "blanket": the reviewer accepted all
    # unjudged items in bulk (their statement is kept); reports must show this, never hide it.
    attestation: Literal["per_item", "blanket"] = "per_item"
    statement: str = ""
    imported_at: datetime


def _fail(path: Path, message: str) -> ConfigError:
    return ConfigError([(str(path), message)])


@dataclass(frozen=True)
class Blanket:
    """A reviewer's bulk acceptance of every unjudged item, given explicitly by that person."""

    reviewer: str
    reviewed_on: str
    statement: str


def import_review(
    sheet_path: Path, report_path: Path, blanket: Blanket | None = None
) -> HumanReview:
    try:
        sheet = yaml.safe_load(sheet_path.read_text())
        report_raw = report_path.read_text()
    except (OSError, yaml.YAMLError) as exc:
        raise _fail(sheet_path, f"cannot read: {exc}") from exc
    report = SuiteRunReport.model_validate_json(report_raw)
    if not isinstance(sheet, dict):
        raise _fail(sheet_path, "not a review sheet")
    reference = sheet.get("run_reference") or {}
    if reference.get("sha256") != hashlib.sha256(report_raw.encode()).hexdigest():
        raise _fail(sheet_path, "the sheet does not belong to this run report")
    reviewer, reviewed_on = sheet.get("reviewer"), sheet.get("reviewed_on")
    if blanket is not None:
        if not (
            blanket.reviewer.strip() and blanket.reviewed_on.strip() and blanket.statement.strip()
        ):
            raise _fail(
                sheet_path, "a blanket acceptance needs the reviewer, the date and their statement"
            )
        reviewer, reviewed_on = blanket.reviewer, blanket.reviewed_on
    if not reviewer or not reviewed_on:
        raise _fail(sheet_path, "reviewer and reviewed_on must be filled in by the human reviewer")
    results = {c.id: c for c in report.cases}
    problems: list[str] = []
    claim_marks: dict[str, list[bool]] = {}
    fact_scores: dict[str, list[float]] = {}
    unreviewed_claims = unreviewed_facts = 0
    for entry in sheet.get("cases", []):
        case_id = str(entry.get("id"))
        result = results.get(case_id)
        if result is None:
            problems.append(f"case {case_id} is not in the run")
            continue
        for claim in entry.get("claims", []):
            if claim.get("claim_id") != claim_id(case_id, str(claim.get("text", ""))):
                problems.append(f"case {case_id}: claim text or id was changed")
                continue
            judgement = claim.get("judgement")
            if judgement is None and blanket is not None:
                judgement = "supported"  # accepted in bulk by the reviewer (attestation: blanket)
            if judgement is None:
                unreviewed_claims += 1
            elif judgement not in CLAIM_VALUES:
                problems.append(f"case {case_id}: unknown claim judgement {judgement!r}")
            elif judgement != "not_factual":
                claim_marks.setdefault(result.category, []).append(judgement == "supported")
        if result.answerable:
            scores = []
            for fact in entry.get("facts", []):
                if not fact.get("required", True):
                    continue
                judgement = fact.get("judgement")
                if judgement is None and blanket is not None:
                    judgement = "covered"  # accepted in bulk by the reviewer (attestation: blanket)
                if judgement is None:
                    unreviewed_facts += 1
                elif judgement not in FACT_VALUES:
                    problems.append(f"case {case_id}: unknown fact judgement {judgement!r}")
                else:
                    scores.append(FACT_VALUES[judgement])
            if scores:
                fact_scores.setdefault(result.category, []).append(sum(scores) / len(scores))
    if problems:
        raise ConfigError([(str(sheet_path), p) for p in problems])

    def ratio(marks: list[bool]) -> Metric:
        return Metric(
            value=sum(marks) / len(marks) if marks else None,
            numerator=sum(marks),
            denominator=len(marks),
        )

    def mean(values: list[float]) -> Metric:
        return Metric(
            value=sum(values) / len(values) if values else None,
            numerator=round(sum(values), 4),
            denominator=len(values),
        )

    all_marks = [m for marks in claim_marks.values() for m in marks]
    all_scores = [s for scores in fact_scores.values() for s in scores]
    return HumanReview(
        reviewer=str(reviewer),
        reviewed_on=str(reviewed_on),
        run_reference={"file": str(reference.get("file")), "sha256": str(reference.get("sha256"))},
        split=report.split,
        run=report.run,
        snapshot_id=report.snapshot_id,
        model=report.model,
        freeze=report.freeze,
        support_precision=ratio(all_marks),
        support_precision_by_category={k: ratio(v) for k, v in sorted(claim_marks.items())},
        required_fact_coverage=mean(all_scores),
        required_fact_coverage_by_category={k: mean(v) for k, v in sorted(fact_scores.items())},
        unreviewed_claims=unreviewed_claims,
        unreviewed_facts=unreviewed_facts,
        attestation="blanket" if blanket is not None else "per_item",
        statement=blanket.statement if blanket is not None else "",
        imported_at=datetime.now(UTC),
    )
