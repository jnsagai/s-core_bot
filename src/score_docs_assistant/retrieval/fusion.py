"""Exact-first reciprocal-rank fusion, dedup, per-document cap, tie-breaks (research R4).

`fusion_version` 1: exact/alias hits first in the given order; the rest by descending RRF sum
(ranks start at 1) with ties broken by (document_key, ordinal). A chunk is skipped when already
emitted, when identical text from the same source was emitted, or when its document reached the
cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FUSION_VERSION = 1
_LABEL_ORDER = {"exact": 0, "alias": 1, "keyword": 2, "semantic": 3}


@dataclass(frozen=True)
class ChunkMeta:
    document_key: str
    source_id: str
    ordinal: int
    content_hash: str


@dataclass(frozen=True)
class Selected:
    rank: int
    rowid: int
    matched_by: list[str] = field(default_factory=list)
    ranking_value: float | None = None


def fuse(
    exact: list[tuple[int, str]],
    keyword: list[int],
    semantic: list[int],
    meta: dict[int, ChunkMeta],
    constant: int,
    limit: int,
    per_document: int,
) -> list[Selected]:
    labels: dict[int, set[str]] = {}
    rrf: dict[int, float] = {}
    for name, ranked in (("keyword", keyword), ("semantic", semantic)):
        for position, rowid in enumerate(ranked, start=1):
            labels.setdefault(rowid, set()).add(name)
            rrf[rowid] = rrf.get(rowid, 0.0) + 1.0 / (constant + position)
    exact_rows: list[int] = []
    for rowid, kind in exact:
        labels.setdefault(rowid, set()).add(kind)
        if rowid not in exact_rows:
            exact_rows.append(rowid)
    fused = sorted(
        (r for r in rrf if r not in exact_rows),
        key=lambda r: (-rrf[r], meta[r].document_key, meta[r].ordinal),
    )
    selected: list[Selected] = []
    seen_text: set[tuple[str, str]] = set()
    per_doc: dict[str, int] = {}
    for rowid in [*exact_rows, *fused]:
        if len(selected) == limit:
            break
        info = meta[rowid]
        text_key = (info.source_id, info.content_hash)
        if text_key in seen_text or per_doc.get(info.document_key, 0) >= per_document:
            continue
        seen_text.add(text_key)
        per_doc[info.document_key] = per_doc.get(info.document_key, 0) + 1
        selected.append(
            Selected(
                rank=len(selected) + 1,
                rowid=rowid,
                matched_by=sorted(labels[rowid], key=_LABEL_ORDER.__getitem__),
                ranking_value=None if rowid in exact_rows else rrf[rowid],
            )
        )
    return selected
