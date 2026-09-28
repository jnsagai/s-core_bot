"""Keyword candidates over the snapshot's FTS5 index (FR-007, FR-008, research R2).

Filters sit in the same statement as the `MATCH` and the bm25 ordering, so ranking runs only over
the filtered set. The expression comes from `query.fts_expression` (quoted literals only).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

# Column weights: text, heading path, need IDs (an ID-column hit outranks prose mentions).
BM25 = "bm25(chunks_fts, 1.0, 0.5, 2.0)"


def keyword_candidates(
    conn: sqlite3.Connection,
    expression: str | None,
    *,
    limit: int,
    sources: Sequence[str] = (),
    kinds: Sequence[str] = (),
) -> list[int]:
    """Chunk rowids, best first (bm25, then rowid for determinism)."""
    if expression is None:
        return []
    clauses = ["chunks_fts MATCH ?"]
    params: list[object] = [expression]
    if sources:
        clauses.append(f"c.source_id IN ({','.join('?' * len(sources))})")
        params.extend(sources)
    if kinds:
        clauses.append(f"c.kind IN ({','.join('?' * len(kinds))})")
        params.extend(kinds)
    params.append(limit)
    sql = (
        "SELECT c.rowid FROM chunks_fts JOIN chunks c ON c.rowid = chunks_fts.rowid "
        f"WHERE {' AND '.join(clauses)} ORDER BY {BM25}, c.rowid LIMIT ?"
    )
    return [row[0] for row in conn.execute(sql, params)]
