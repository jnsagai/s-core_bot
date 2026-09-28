"""Exact cosine search over a snapshot's unit-norm float32 vectors (FR-008, research R3).

Filtered-out rows are excluded before selection (filter before rank). Vectors are L2-normalized
(F003), so the dot product is the cosine. Ties are broken by row for determinism.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

Vector = npt.NDArray[np.float32]
Mask = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class RowAttributes:
    """Row-aligned source IDs and kinds for building filter masks (loaded once per snapshot)."""

    source_ids: npt.NDArray[Any]
    kinds: npt.NDArray[Any]

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> RowAttributes:
        rows = conn.execute("SELECT source_id, kind FROM chunks ORDER BY rowid").fetchall()
        return cls(
            source_ids=np.array([r[0] for r in rows], dtype=object),
            kinds=np.array([r[1] for r in rows], dtype=object),
        )

    def mask(self, sources: list[str], kinds: list[str]) -> Mask | None:
        if not sources and not kinds:
            return None
        mask = np.ones(len(self.source_ids), dtype=bool)
        if sources:
            mask &= np.isin(self.source_ids, sources)
        if kinds:
            mask &= np.isin(self.kinds, kinds)
        return mask


def top_k(matrix: Vector, query: Vector, mask: Mask | None, k: int) -> list[int]:
    """1-based rowids of the k best rows, best first."""
    if matrix.shape[0] == 0 or k <= 0:
        return []
    scores = np.asarray(matrix, dtype=np.float32) @ np.asarray(query, dtype=np.float32)
    if mask is not None:
        scores = np.where(mask, scores, -np.inf)
    allowed = int(np.count_nonzero(np.isfinite(scores)))
    k = min(k, allowed)
    if k == 0:
        return []
    rows = np.arange(scores.shape[0])
    # lexsort: last key is primary → sort by -score, then by row.
    order = np.lexsort((rows, -scores))[:k]
    return [int(r) + 1 for r in order]


def normalize(vector: list[float], dimension: int) -> Vector | None:
    array = np.asarray(vector, dtype=np.float64)
    if array.shape != (dimension,) or not np.all(np.isfinite(array)):
        return None
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        return None
    return (array / norm).astype(np.float32)
