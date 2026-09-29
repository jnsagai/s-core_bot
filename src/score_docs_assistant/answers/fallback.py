"""Extractive fallback after failed validation (FR-008, research R5).

Only stored excerpts, verbatim (bounded at a word boundary), each citing its own evidence ID, plus
one limitation. No model text is ever included. Excerpts that the answer rules would not allow in a
claim are skipped rather than edited: text addressed to AI assistants, links (URL rule), and
evidence-ID-like markers such as "[E9]" (F008 adversarial finding: the fallback relayed malicious
links and fake citation markers verbatim).
"""

from __future__ import annotations

from collections.abc import Sequence

from score_docs_assistant.answers.prompt import EvidenceItem
from score_docs_assistant.answers.validate import EVIDENCE_MARKER, URL_PATTERN
from score_docs_assistant.domain.answers import Claim
from score_docs_assistant.retrieval.query import excerpt

FALLBACK_CHARACTERS = 600
FALLBACK_LIMITATION = (
    "The model's answer failed validation; these are the most relevant excerpts, "
    "not a composed answer."
)


def presentable(item: EvidenceItem) -> bool:
    text = item.result.excerpt
    return not (item.suspicious or URL_PATTERN.search(text) or EVIDENCE_MARKER.search(text))


def extractive_fallback(evidence: Sequence[EvidenceItem], count: int) -> list[Claim]:
    claims = [
        Claim(
            text=excerpt(item.result.excerpt, FALLBACK_CHARACTERS)[0],
            kind="documented",
            evidence_ids=[item.evidence_id],
        )
        for item in [e for e in evidence if presentable(e)][:count]
    ]
    claims.append(Claim(text=FALLBACK_LIMITATION, kind="limitation", evidence_ids=[]))
    return claims
