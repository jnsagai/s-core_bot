"""Comparison prompt: two side-namespaced, escaped evidence blocks (research R2).

Each side contributes the evidence items its own answer used, cited items first, relabelled
L1…/R1…. The evidence budget follows F005's arithmetic and is split evenly between the sides; a
side may use what the other leaves. Whole excerpts only; reductions are reported.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from score_docs_assistant.answers.prompt import SAFETY_MARGIN_TOKENS, EvidenceItem, escape
from score_docs_assistant.comparison.policy import COMPARISON_POLICY
from score_docs_assistant.ingestion.tokens import estimate_tokens


@dataclass
class ComparisonPrompt:
    messages: list[dict[str, str]]
    left: list[EvidenceItem]
    right: list[EvidenceItem]
    warnings: list[str] = field(default_factory=list)

    def evidence_map(self) -> dict[str, EvidenceItem]:
        return {e.evidence_id: e for e in [*self.left, *self.right]}


def _attribute(value: str) -> str:
    return escape(value).replace('"', "'")


def render_excerpt(item: EvidenceItem) -> str:
    result = item.result
    section = " > ".join(result.heading_path)
    untrusted = ' untrusted="instructions-like"' if item.suspicious else ""
    return (
        f'<excerpt id="{item.evidence_id}" source="{_attribute(result.source_id)}" '
        f'path="{_attribute(result.path)}" section="{_attribute(section)}"{untrusted}>\n'
        f"{item.shown}\n</excerpt>"
    )


def relabel(items: Sequence[EvidenceItem], prefix: str) -> list[EvidenceItem]:
    """Renumber as L1…/R1…; the shown text is re-escaped from the stored excerpt."""
    out: list[EvidenceItem] = []
    for index, item in enumerate(items, start=1):
        shown = escape(item.result.excerpt)
        draft = EvidenceItem(f"{prefix}{index}", item.result, shown, 0, item.suspicious)
        out.append(
            EvidenceItem(
                evidence_id=draft.evidence_id,
                result=item.result,
                shown=shown,
                tokens=estimate_tokens(render_excerpt(draft)),
                suspicious=item.suspicious,
            )
        )
    return out


def order_side(items: Sequence[EvidenceItem], cited: set[str], limit: int) -> list[EvidenceItem]:
    """Cited items first (in prompt order), then the rest; at most `limit`."""
    first = [i for i in items if i.evidence_id in cited]
    rest = [i for i in items if i.evidence_id not in cited]
    return [*first, *rest][:limit]


def _fit(items: list[EvidenceItem], budget: int) -> list[EvidenceItem]:
    kept: list[EvidenceItem] = []
    used = 0
    for item in items:
        if used + item.tokens > budget:
            break
        kept.append(item)
        used += item.tokens
    return kept


def build_comparison_prompt(
    question: str,
    left_snapshot: str,
    right_snapshot: str,
    left: Sequence[EvidenceItem],
    right: Sequence[EvidenceItem],
    *,
    evidence_tokens: int,
    context_tokens: int,
    output_tokens: int,
) -> ComparisonPrompt:
    """`left`/`right` must already be relabelled (L…/R…) and ordered."""
    question_block = f"<question>\n{escape(question)}\n</question>"
    fixed = estimate_tokens(COMPARISON_POLICY) + estimate_tokens(question_block) + 40
    available = context_tokens - output_tokens - fixed - SAFETY_MARGIN_TOKENS
    budget = max(min(evidence_tokens, available), 0)
    half = budget // 2
    left_kept = _fit(list(left), half)
    right_kept = _fit(list(right), budget - sum(i.tokens for i in left_kept))
    if len(right_kept) == len(right) and len(left_kept) < len(left):
        left_kept = _fit(list(left), budget - sum(i.tokens for i in right_kept))
    warnings: list[str] = []
    dropped_left, dropped_right = len(left) - len(left_kept), len(right) - len(right_kept)
    if dropped_left or dropped_right:
        warnings.append(
            f"comparison_evidence_reduced: left {dropped_left}, right {dropped_right} excerpt(s) "
            "did not fit"
        )

    def block(tag: str, snapshot: str, items: list[EvidenceItem]) -> str:
        body = "\n".join(render_excerpt(i) for i in items) if items else "(no evidence)"
        return f'<{tag} snapshot="{_attribute(snapshot)}">\n{body}\n</{tag}>'

    user = "\n\n".join(
        [
            block("left_evidence", left_snapshot, left_kept),
            block("right_evidence", right_snapshot, right_kept),
            question_block,
        ]
    )
    return ComparisonPrompt(
        messages=[
            {"role": "system", "content": COMPARISON_POLICY},
            {"role": "user", "content": user},
        ],
        left=left_kept,
        right=right_kept,
        warnings=warnings,
    )
