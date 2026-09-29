"""Validation of comparison drafts (FR-004–FR-008, research R3, contracts/comparison-schema.md).

The model never supplies coverage reasons, and absence is never stated as removal: any wording
that asserts removal, deletion or addition is rejected. Each difference is checked on its own; the
caller decides whether a structurally valid output with rejected differences may be salvaged.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from score_docs_assistant.answers.injection import reads_as_advice
from score_docs_assistant.answers.prompt import EvidenceItem
from score_docs_assistant.answers.validate import MAX_RAW_BYTES, MIN_QUOTE_CHARACTERS
from score_docs_assistant.domain.comparison import DifferenceType

_URL = re.compile(r"(https?://|www\.|file:|mailto:)", re.IGNORECASE)
_THOUGHT = re.compile(r"</?think>|<\|thinking\|>", re.IGNORECASE)
_QUOTES = (
    re.compile(r'"([^"\n]{' + str(MIN_QUOTE_CHARACTERS) + r',})"'),
    re.compile(r"`([^`\n]{" + str(MIN_QUOTE_CHARACTERS) + r",})`"),
)
DELETION_WORDING = re.compile(
    r"\b(remov(e|ed|es|al|ing)|delet(e|ed|es|ion|ing)|dropped|discontinued|eliminated|"
    r"no\s+longer|adds|added|introduc(es|ed|ing))\b",
    re.IGNORECASE,
)
_LEFT = re.compile(r"^L[0-9]{1,2}$")
_RIGHT = re.compile(r"^R[0-9]{1,2}$")


class _DraftDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: DifferenceType
    statement: str
    left_evidence_ids: list[str]
    right_evidence_ids: list[str]


class _Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    differences: list[_DraftDifference] = Field(default_factory=list)


@dataclass(frozen=True)
class ValidDifference:
    type: DifferenceType
    statement: str
    left_evidence_ids: list[str]
    right_evidence_ids: list[str]


@dataclass
class ComparisonOutcome:
    differences: list[ValidDifference] = field(default_factory=list)  # each passed every check
    errors: list[str] = field(default_factory=list)
    structural: bool = False  # parsed, matched the schema and the size limit
    rejected: int = 0  # differences that failed at least one check

    @property
    def ok(self) -> bool:
        return not self.errors


def _normalize(text: str) -> str:
    return " ".join(text.split())


def validate_comparison(
    raw: str,
    *,
    truncated: bool,
    evidence: dict[str, EvidenceItem],
    max_differences: int,
    max_statement_characters: int,
) -> ComparisonOutcome:
    outcome = ComparisonOutcome()
    errors = outcome.errors
    if truncated or len(raw.encode("utf-8")) > MAX_RAW_BYTES:
        errors.append("JSON_INVALID: output was cut off (length or size limit)")
        return outcome
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        errors.append("JSON_INVALID: output is not JSON")
        return outcome
    if not isinstance(data, dict):
        errors.append("JSON_INVALID: output is not a JSON object")
        return outcome
    try:
        draft = _Draft.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        errors.append(f"SCHEMA_INVALID: {fields}")
        return outcome
    if len(draft.differences) > max_differences:
        errors.append(f"SCHEMA_INVALID: more than {max_differences} differences")
        return outcome
    outcome.structural = True
    for index, d in enumerate(draft.differences):
        label = f"difference {index + 1}"
        statement = d.statement.strip()
        before = len(errors)
        if not statement:
            errors.append(f"EMPTY_STATEMENT: {label}")
            outcome.rejected += 1
            continue
        if len(statement) > max_statement_characters:
            errors.append(
                f"SCHEMA_INVALID: {label} longer than {max_statement_characters} characters"
            )
        wrong = [e for e in d.left_evidence_ids if not _LEFT.match(e)] + [
            e for e in d.right_evidence_ids if not _RIGHT.match(e)
        ]
        if wrong:
            errors.append(f"WRONG_SIDE_ID: {label} cites {wrong} on the wrong side")
        cited = [*d.left_evidence_ids, *d.right_evidence_ids]
        unknown = [e for e in cited if e not in evidence]
        if unknown:
            errors.append(f"UNKNOWN_EVIDENCE_ID: {label} cites {unknown}")
        both = bool(d.left_evidence_ids) and bool(d.right_evidence_ids)
        if d.type == "not_established":
            if both or not cited:
                errors.append(
                    f"ONE_SIDE_ONLY: {label} (not_established) must cite exactly one side"
                )
        elif not both:
            errors.append(f"MISSING_SIDE_EVIDENCE: {label} ({d.type}) must cite both sides")
        items = [evidence[e] for e in cited if e in evidence]
        if d.type == "changed" and both and not unknown:
            left_texts = {_normalize(evidence[e].result.excerpt) for e in d.left_evidence_ids}
            right_texts = {_normalize(evidence[e].result.excerpt) for e in d.right_evidence_ids}
            if left_texts <= right_texts:
                errors.append(
                    f"CHANGED_WITHOUT_DIFFERENCE: {label} cites identical excerpts on both sides"
                )
        if DELETION_WORDING.search(statement):
            errors.append(
                f"DELETION_CLAIM: {label} states removal or addition; absence is not_established"
            )
        if _URL.search(statement):
            errors.append(f"URL_IN_TEXT: {label}")
        if _THOUGHT.search(statement):
            errors.append(f"HIDDEN_THOUGHT: {label}")
        if any(i.suspicious for i in items) and reads_as_advice(statement):
            errors.append(
                f"INJECTION_SUSPECTED: {label} turns text addressed to AI assistants into advice"
            )
        haystacks = [_normalize(i.result.excerpt) for i in items] + [
            _normalize(i.shown) for i in items
        ]
        for pattern in _QUOTES:
            for quoted in pattern.findall(statement):
                if not any(_normalize(quoted) in hay for hay in haystacks):
                    errors.append(f"QUOTE_NOT_IN_EVIDENCE: {label} quotes text not in its evidence")
        if len(errors) > before:
            outcome.rejected += 1
            continue
        outcome.differences.append(
            ValidDifference(
                type=d.type,
                statement=statement,
                left_evidence_ids=list(dict.fromkeys(d.left_evidence_ids)),
                right_evidence_ids=list(dict.fromkeys(d.right_evidence_ids)),
            )
        )
    return outcome
