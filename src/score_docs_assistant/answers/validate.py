"""Validation of model drafts (FR-003, FR-005, FR-007, contracts/answer-schema.md, research R4).

The model's status is not trusted on its own: status and claims must be consistent (a real run
returned `insufficient_evidence` together with documented, cited claims).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from score_docs_assistant.answers.injection import reads_as_advice
from score_docs_assistant.answers.prompt import EvidenceItem
from score_docs_assistant.domain.answers import AnswerStatus, Claim, ClaimKind

MAX_RAW_BYTES = 64 * 1024
MIN_QUOTE_CHARACTERS = 12
NORMALIZED_PARTIAL = "The supplied evidence may answer only part of this question."
NORMALIZED_CLARIFICATION = "More context (for example the release or module) is needed."
_URL = re.compile(r"(https?://|www\.|file:|mailto:)", re.IGNORECASE)
_THOUGHT = re.compile(r"</?think>|<\|thinking\|>", re.IGNORECASE)
_QUOTES = (
    re.compile(r'"([^"\n]{' + str(MIN_QUOTE_CHARACTERS) + r',})"'),
    re.compile(r"`([^`\n]{" + str(MIN_QUOTE_CHARACTERS) + r",})`"),
)


class _DraftClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    kind: ClaimKind
    evidence_ids: list[str]


class _Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AnswerStatus
    claims: list[_DraftClaim] = Field(default_factory=list)


@dataclass
class ValidationOutcome:
    status: AnswerStatus | None = None
    claims: list[Claim] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.status is not None


def _normalize(text: str) -> str:
    return " ".join(text.split())


def validate_draft(
    raw: str,
    *,
    truncated: bool,
    evidence: dict[str, EvidenceItem],
    max_claims: int,
    max_claim_characters: int,
) -> ValidationOutcome:
    outcome = ValidationOutcome()
    if truncated or len(raw.encode("utf-8")) > MAX_RAW_BYTES:
        outcome.errors.append("JSON_INVALID: output was cut off (length or size limit)")
        return outcome
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        outcome.errors.append("JSON_INVALID: output is not JSON")
        return outcome
    if not isinstance(data, dict):
        outcome.errors.append("JSON_INVALID: output is not a JSON object")
        return outcome
    try:
        draft = _Draft.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        outcome.errors.append(f"SCHEMA_INVALID: {fields}")
        return outcome
    errors = outcome.errors
    if len(draft.claims) > max_claims:
        errors.append(f"SCHEMA_INVALID: more than {max_claims} claims")
    for index, claim in enumerate(draft.claims):
        label = f"claim {index + 1}"
        if not claim.text.strip():
            errors.append(f"EMPTY_CLAIM: {label}")
            continue
        if len(claim.text) > max_claim_characters:
            errors.append(f"SCHEMA_INVALID: {label} longer than {max_claim_characters} characters")
        unknown = [e for e in claim.evidence_ids if e not in evidence]
        if unknown:
            errors.append(f"UNKNOWN_EVIDENCE_ID: {label} cites {unknown}")
        if claim.kind in ("documented", "interpretation") and not claim.evidence_ids:
            errors.append(f"MISSING_CITATION: {label} ({claim.kind}) cites no evidence")
        if any(
            evidence[e].suspicious for e in claim.evidence_ids if e in evidence
        ) and reads_as_advice(claim.text):
            errors.append(
                f"INJECTION_SUSPECTED: {label} turns text addressed to AI assistants into advice"
            )
        if _URL.search(claim.text):
            errors.append(f"URL_IN_TEXT: {label}")
        if _THOUGHT.search(claim.text):
            errors.append(f"HIDDEN_THOUGHT: {label}")
        cited = [evidence[e] for e in claim.evidence_ids if e in evidence] or list(
            evidence.values()
        )
        haystacks = [_normalize(i.result.excerpt) for i in cited] + [
            _normalize(i.shown) for i in cited
        ]
        for pattern in _QUOTES:
            for quoted in pattern.findall(claim.text):
                needle = _normalize(quoted)
                if not any(needle in hay for hay in haystacks):
                    errors.append(f"QUOTE_NOT_IN_EVIDENCE: {label} quotes text not in its evidence")
    claims = [
        Claim(text=c.text.strip(), kind=c.kind, evidence_ids=list(dict.fromkeys(c.evidence_ids)))
        for c in draft.claims
        if c.text.strip()
    ]
    kinds = [c.kind for c in claims]
    documented = kinds.count("documented")
    status: AnswerStatus = draft.status
    # The status is metadata; the claims are validated independently. Benign status mismatches
    # (observed often with the local model) are normalized with a server-authored gap statement
    # instead of discarding validated, cited claims. Only an answer without any documented claim
    # is rejected (research R4 as amended).
    if status in ("answered", "partial") and documented == 0:
        errors.append(f"STATUS_INCONSISTENT: status {status} without a documented claim")
    elif status == "insufficient_evidence" and (documented or "interpretation" in kinds):
        status = "partial"
        outcome.notes.append("status_normalized: insufficient_evidence with cited claims → partial")
        claims.append(Claim(text=NORMALIZED_PARTIAL, kind="limitation"))
    elif status == "partial" and "limitation" not in kinds:
        outcome.notes.append("status_normalized: partial without a stated gap")
        claims.append(Claim(text=NORMALIZED_PARTIAL, kind="limitation"))
    elif status == "clarification_needed" and "limitation" not in kinds:
        outcome.notes.append("status_normalized: clarification_needed without a stated need")
        claims.append(Claim(text=NORMALIZED_CLARIFICATION, kind="limitation"))
    outcome.status = status
    outcome.claims = claims
    return outcome
