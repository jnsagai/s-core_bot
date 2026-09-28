"""`embeddings.f32`: raw little-endian float32, C order, rows × dimension (FR-007, research R5).

No header and no pickle: the shape lives in `embedding-manifest.json` and is checked against the
file size before any read.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt

from score_docs_assistant.domain.errors import SnapshotError

DTYPE = np.dtype("<f4")
NORM_TOLERANCE = 1e-3

Matrix = npt.NDArray[np.float32]


def normalize_rows(vectors: Sequence[Sequence[float]], dimension: int) -> Matrix:
    """float32 + L2 normalization; rejects wrong dimension, non-finite and zero vectors."""
    for index, vector in enumerate(vectors):
        if len(vector) != dimension:
            raise SnapshotError(
                "EMBEDDING_INVALID_VECTOR",
                f"vector {index} has dimension {len(vector)}, expected {dimension}",
            )
    matrix = np.asarray(vectors, dtype=np.float64).reshape(len(vectors), dimension)
    if not np.all(np.isfinite(matrix)):
        raise SnapshotError("EMBEDDING_INVALID_VECTOR", "vector contains a non-finite value")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise SnapshotError("EMBEDDING_INVALID_VECTOR", "vector has zero norm")
    return (matrix / norms).astype(DTYPE)


def write_vectors(path: Path, matrix: Matrix) -> None:
    if path.exists():
        raise FileExistsError(path)
    np.ascontiguousarray(matrix, dtype=DTYPE).tofile(path)


def open_vectors(path: Path, rows: int, dimension: int) -> Matrix:
    expected = rows * dimension * DTYPE.itemsize
    actual = path.stat().st_size
    if actual != expected:
        raise SnapshotError(
            "CHECKSUM_MISMATCH",
            f"{path.name}: size {actual} bytes, expected {rows} × {dimension} × 4 = {expected}",
        )
    if rows == 0:
        return np.zeros((0, dimension), dtype=DTYPE)
    memmap: Matrix = np.memmap(path, dtype=DTYPE, mode="r", shape=(rows, dimension))
    return memmap


def vector_problems(matrix: Matrix) -> list[str]:
    """Integrity problems (empty list = valid): non-finite values, rows off unit norm."""
    problems: list[str] = []
    if matrix.size == 0:
        return problems
    finite = np.isfinite(matrix).all(axis=1)
    if not finite.all():
        problems.append(f"{int((~finite).sum())} row(s) contain non-finite values")
    norms = np.linalg.norm(matrix.astype(np.float64), axis=1)
    bad = np.abs(norms - 1.0) > NORM_TOLERANCE
    bad &= finite
    if bad.any():
        problems.append(f"{int(bad.sum())} row(s) are not unit norm (±{NORM_TOLERANCE})")
    return problems
