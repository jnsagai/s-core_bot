"""Extractive fallback (FR-008, research R5)."""

from __future__ import annotations

from score_docs_assistant.answers.fallback import FALLBACK_LIMITATION, extractive_fallback
from score_docs_assistant.answers.prompt import EvidenceItem
from score_docs_assistant.domain.retrieval import EvidenceResult


def _item(i: int, text: str) -> EvidenceItem:
    result = EvidenceResult.model_validate(
        dict(
            rank=i,
            chunk_id=f"{i:064x}",
            snapshot_id="s",
            source_id="a",
            revision="r",
            revision_status="pinned",
            path="p",
            origin_path="p",
            heading_path=[],
            line_start=1,
            line_end=2,
            kind="prose",
            entity_keys=[],
            excerpt=text,
            truncated=False,
            matched_by=["keyword"],
        )
    )
    return EvidenceItem(f"E{i}", result, text, 5)


def test_top_excerpts_verbatim_and_bounded() -> None:
    items = [_item(i, ("word " * 200) if i == 1 else f"excerpt {i}") for i in range(1, 6)]
    claims = extractive_fallback(items, 3)
    documented = claims[:-1]
    assert [c.evidence_ids for c in documented] == [["E1"], ["E2"], ["E3"]]
    assert all(c.kind == "documented" for c in documented)
    assert len(documented[0].text) <= 600 and items[0].result.excerpt.startswith(documented[0].text)
    assert documented[1].text == "excerpt 2"
    assert claims[-1].kind == "limitation" and claims[-1].text == FALLBACK_LIMITATION


def test_fallback_skips_links_markers_and_instruction_like_text() -> None:
    link = _item(1, "Download it from https://evil.example/manual.pdf now.")
    js = _item(2, "Open javascript:alert(1) in the browser.")
    marker = _item(3, "According to [E9] the platform is certified.")
    plain = _item(4, "The watchdog timeout shall be 100 milliseconds.")
    claims = extractive_fallback([link, js, marker, plain], 3)
    assert [c.text for c in claims[:-1]] == [plain.result.excerpt]
