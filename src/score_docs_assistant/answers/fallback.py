"""Extractive fallback after failed validation (FR-008, research R5).

Only stored excerpts, verbatim (bounded at a word boundary), each citing its own evidence ID, plus
one limitation. No model text is ever included.
"""

from __future__ import annotations

from collections.abc import Sequence

from score_docs_assistant.answers.prompt import EvidenceItem
from score_docs_assistant.domain.answers import Claim
from score_docs_assistant.retrieval.query import excerpt

FALLBACK_CHARACTERS = 600
FALLBACK_LIMITATION = (
    "The model's answer failed validation; these are the most relevant excerpts, "
    "not a composed answer."
)


def extractive_fallback(evidence: Sequence[EvidenceItem], count: int) -> list[Claim]:
    claims = [
        Claim(
            text=excerpt(item.result.excerpt, FALLBACK_CHARACTERS)[0],
            kind="documented",
            evidence_ids=[item.evidence_id],
        )
        for item in evidence[:count]
    ]
    claims.append(Claim(text=FALLBACK_LIMITATION, kind="limitation", evidence_ids=[]))
    return claims
