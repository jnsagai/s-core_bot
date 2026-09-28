"""Citations from stored provenance only (FR-004, research R6)."""

from __future__ import annotations

import json
from pathlib import Path

from score_docs_assistant.answers.citations import SourceLinks, build_citations
from score_docs_assistant.answers.prompt import EvidenceItem
from score_docs_assistant.domain.answers import Claim
from score_docs_assistant.domain.retrieval import EvidenceResult


def _item(eid: str, **kw: object) -> EvidenceItem:
    base = dict(
        rank=1,
        chunk_id="c" * 64,
        snapshot_id="s",
        source_id="score-process",
        revision="a" * 40,
        revision_status="pinned",
        path="process/x y.rst",
        origin_path="process/x y.rst",
        heading_path=["H"],
        line_start=10,
        line_end=20,
        kind="prose",
        entity_keys=[],
        excerpt="stored excerpt",
        truncated=False,
        matched_by=["keyword"],
    )
    result = EvidenceResult.model_validate({**base, **kw})
    return EvidenceItem(evidence_id=eid, result=result, shown=result.excerpt, tokens=5)


def _lock(tmp_path: Path, repo: str, revision: str = "a" * 40, kind: str = "git") -> Path:
    path = tmp_path / "source-lock.json"
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "score-process",
                        "kind": kind,
                        "repository": repo,
                        "revision": revision,
                    }
                ]
            }
        )
    )
    return path


def test_github_immutable_url(tmp_path: Path) -> None:
    links = SourceLinks.from_lock(
        _lock(tmp_path, "https://github.com/eclipse-score/process_description.git")
    )
    [citation] = build_citations(
        [Claim(text="t", kind="documented", evidence_ids=["E1"])], {"E1": _item("E1")}, links
    )
    assert citation.immutable_url == (
        "https://github.com/eclipse-score/process_description/blob/"
        + "a" * 40
        + "/process/x%20y.rst#L10-L20"
    )
    assert citation.revision_match == "exact" and citation.excerpt == "stored excerpt"
    assert citation.chunk_id == "c" * 64 and citation.snapshot_id == "s"


def test_no_url_without_exact_revision_or_allowed_host(tmp_path: Path) -> None:
    claim = [Claim(text="t", kind="documented", evidence_ids=["E1"])]
    for lock in (
        _lock(tmp_path, "https://github.com/o/r.git", revision="b" * 40),
        _lock(tmp_path, "https://gitlab.com/o/r.git"),
        _lock(tmp_path, "https://github.com/o/r.git", kind="needs-export"),
    ):
        [citation] = build_citations(claim, {"E1": _item("E1")}, SourceLinks.from_lock(lock))
        assert citation.immutable_url is None and citation.revision_match == "none"
    export = _item("E1", revision_status="unverified")
    [citation] = build_citations(
        claim, {"E1": export}, SourceLinks.from_lock(_lock(tmp_path, "https://github.com/o/r"))
    )
    assert citation.immutable_url is None and citation.revision_match == "unverified"
    assert SourceLinks.from_lock(tmp_path / "missing.json").url(_item("E1")) is None


def test_first_use_order_one_per_id(tmp_path: Path) -> None:
    claims = [
        Claim(text="a", kind="documented", evidence_ids=["E2", "E1"]),
        Claim(text="b", kind="interpretation", evidence_ids=["E1"]),
        Claim(text="c", kind="limitation", evidence_ids=[]),
    ]
    citations = build_citations(claims, {"E1": _item("E1"), "E2": _item("E2")}, SourceLinks({}))
    assert [c.evidence_id for c in citations] == ["E2", "E1"]


def test_lines_unknown_no_anchor(tmp_path: Path) -> None:
    links = SourceLinks.from_lock(_lock(tmp_path, "https://github.com/o/r.git"))
    assert links.url(_item("E1", line_start=None, line_end=None)).endswith("/process/x%20y.rst")  # type: ignore[union-attr]
