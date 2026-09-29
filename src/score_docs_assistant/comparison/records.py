"""Exact requirement-record comparison across two snapshots (FR-011, research R5b).

Record identity is the need ID. The fingerprint is the type, title, status, options and the text
of the record's first chunk; a new path or line range alone is noted but is not a change.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from score_docs_assistant.domain.retrieval import EntityRecord
from score_docs_assistant.retrieval.exact import EntityIndex
from score_docs_assistant.retrieval.query import id_tokens

FULL_TEXT = 10_000_000
Verdict = Literal["unchanged", "changed", "left_only", "right_only"]


@dataclass(frozen=True)
class RecordPair:
    need_id: str
    left: EntityRecord | None
    right: EntityRecord | None
    verdict: Verdict
    changed_fields: tuple[str, ...] = ()
    moved: bool = False


def _first(index: EntityIndex, conn: sqlite3.Connection, need_id: str) -> EntityRecord | None:
    matches = index.match(need_id)
    if not matches:
        return None
    entity, kind = matches[0]
    return index.record(conn, entity, kind, FULL_TEXT)


def _changed_fields(a: EntityRecord, b: EntityRecord) -> tuple[str, ...]:
    fields = [
        name
        for name, x, y in (
            ("type", a.type, b.type),
            ("title", a.title, b.title),
            ("status", a.status, b.status),
            ("options", a.options, b.options),
        )
        if x != y
    ]
    if " ".join((a.excerpt or "").split()) != " ".join((b.excerpt or "").split()):
        fields.append("text")
    return tuple(fields)


def compare_records(
    question: str,
    left: tuple[EntityIndex, sqlite3.Connection],
    right: tuple[EntityIndex, sqlite3.Connection],
) -> list[RecordPair]:
    """Pairs for every requirement ID in the question that either snapshot recognizes."""
    need_ids: list[str] = []
    for index, _conn in (left, right):
        for entity, _kind in index.match_query(question):
            if entity.need_id not in need_ids:
                need_ids.append(entity.need_id)
    # Keep question order for readability.
    order = {token: n for n, token in enumerate(id_tokens(question))}
    need_ids.sort(key=lambda n: order.get(n, len(order)))
    pairs: list[RecordPair] = []
    for need_id in need_ids:
        a, b = _first(*left, need_id), _first(*right, need_id)
        if a is None and b is None:
            continue
        if a is None:
            pairs.append(RecordPair(need_id, None, b, "right_only"))
        elif b is None:
            pairs.append(RecordPair(need_id, a, None, "left_only"))
        else:
            changed = _changed_fields(a, b)
            moved = (a.path, a.line_start, a.line_end) != (b.path, b.line_start, b.line_end)
            verdict: Verdict = "changed" if changed else "unchanged"
            pairs.append(RecordPair(need_id, a, b, verdict, changed, moved))
    return pairs
