"""Prompt assembly: delimited data blocks, escaping, evidence/history budget (research R2, R3).

Budgets use the conservative `pretoken-v1` estimate, so the prompt never exceeds the model context.
Evidence is packed as whole excerpts in rank order (lowest ranks dropped first); history is dropped
oldest-first. Nothing is ever cut mid-text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from score_docs_assistant.answers.injection import addresses_assistant
from score_docs_assistant.answers.policy import SYSTEM_POLICY
from score_docs_assistant.config.schema import GenerationConfig
from score_docs_assistant.domain.answers import Turn
from score_docs_assistant.domain.retrieval import EvidenceResult
from score_docs_assistant.ingestion.tokens import estimate_tokens

SAFETY_MARGIN_TOKENS = 200
NEW_CONTEXT_WARNING = (
    "new_evidence_context: earlier turns from another or unknown snapshot were not used"
)


def escape(text: str) -> str:
    """Neutralize tag delimiters inside data so documents cannot close or open blocks."""
    return text.replace("<", "‹").replace(">", "›")


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    result: EvidenceResult
    shown: str  # escaped excerpt as sent to the model
    tokens: int
    suspicious: bool = False  # contains text addressed to AI assistants (answers/injection.py)


@dataclass
class Prompt:
    messages: list[dict[str, str]]
    evidence: list[EvidenceItem]
    evidence_dropped: int
    history_used: int
    warnings: list[str] = field(default_factory=list)

    def evidence_map(self) -> dict[str, EvidenceItem]:
        return {e.evidence_id: e for e in self.evidence}


def retrieval_query(question: str, history: Sequence[Turn], max_characters: int) -> str:
    """The question plus the most recent prior user turn; assistant text never steers retrieval."""
    last_user = next((t.content for t in reversed(history) if t.role == "user"), "")
    query = f"{question} {last_user}".strip() if last_user else question
    return query[:max_characters]


def select_history(
    history: Sequence[Turn], snapshot_id: str, *, max_turns: int
) -> tuple[list[Turn], list[str]]:
    """Drop assistant turns bound to another or no snapshot, with the user turn they answered."""
    kept: list[Turn] = []
    excluded = False
    turns = list(history)
    for index, turn in enumerate(turns):
        if turn.role == "assistant" and turn.snapshot_id != snapshot_id:
            excluded = True
            if kept and kept[-1].role == "user" and index > 0 and turns[index - 1] is kept[-1]:
                kept.pop()
            continue
        kept.append(turn)
    warnings = [NEW_CONTEXT_WARNING] if excluded else []
    return kept[-max_turns:] if max_turns else [], warnings


def _attribute(value: str) -> str:
    return escape(value).replace('"', "'")


def _render_excerpt(item: EvidenceItem) -> str:
    result = item.result
    section = " > ".join(result.heading_path)
    untrusted = ' untrusted="instructions-like"' if item.suspicious else ""
    return (
        f'<excerpt id="{item.evidence_id}" source="{_attribute(result.source_id)}" '
        f'path="{_attribute(result.path)}" section="{_attribute(section)}"{untrusted}>\n'
        f"{item.shown}\n</excerpt>"
    )


def build_prompt(
    question: str,
    history: Sequence[Turn],
    results: Sequence[EvidenceResult],
    config: GenerationConfig,
    context_tokens: int,
    output_tokens: int,
) -> Prompt:
    warnings: list[str] = []
    policy_tokens = estimate_tokens(SYSTEM_POLICY)

    # History + question within their budget; the question itself is never cut.
    question_block = f"<question>\n{escape(question)}\n</question>"
    history_budget = max(config.history_tokens - estimate_tokens(question_block), 0)
    turns = list(history)
    rendered: list[str] = [f"{t.role}: {escape(t.content)}" for t in turns]
    while rendered and estimate_tokens("\n".join(rendered)) > history_budget:
        rendered.pop(0)
    if len(rendered) < len(turns):
        warnings.append(f"history_reduced: {len(turns) - len(rendered)} earlier turn(s) not used")
    conversation = "\n".join(rendered) if rendered else "(none)"
    conversation_block = f"<conversation>\n{conversation}\n</conversation>"

    fixed = policy_tokens + estimate_tokens(conversation_block) + estimate_tokens(question_block)
    available = context_tokens - output_tokens - fixed - SAFETY_MARGIN_TOKENS
    evidence_budget = max(min(config.evidence_tokens, available), 0)

    evidence: list[EvidenceItem] = []
    used = 0
    for result in results[: config.evidence_items]:
        shown = escape(result.excerpt)
        suspicious = addresses_assistant(result.excerpt)
        item = EvidenceItem(
            evidence_id=f"E{len(evidence) + 1}",
            result=result,
            shown=shown,
            tokens=0,
            suspicious=suspicious,
        )
        tokens = estimate_tokens(_render_excerpt(item))
        if used + tokens > evidence_budget:
            break
        evidence.append(
            EvidenceItem(
                evidence_id=item.evidence_id,
                result=result,
                shown=shown,
                tokens=tokens,
                suspicious=suspicious,
            )
        )
        used += tokens
    dropped = min(len(results), config.evidence_items) - len(evidence)
    if dropped:
        warnings.append(f"evidence_reduced: {dropped} lower-ranked excerpt(s) did not fit")

    evidence_block = (
        "<evidence>\n" + "\n".join(_render_excerpt(e) for e in evidence) + "\n</evidence>"
    )
    user = f"{conversation_block}\n\n{evidence_block}\n\n{question_block}"
    return Prompt(
        messages=[
            {"role": "system", "content": SYSTEM_POLICY},
            {"role": "user", "content": user},
        ],
        evidence=evidence,
        evidence_dropped=dropped,
        history_used=len(rendered),
        warnings=warnings,
    )
