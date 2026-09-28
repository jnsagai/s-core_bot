"""embeddings.f32 layout and checks (FR-007, research R5)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.vectors import (
    normalize_rows,
    open_vectors,
    vector_problems,
    write_vectors,
)


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    matrix = normalize_rows([[3.0, 4.0], [1.0, 0.0], [0.0, -2.0]], 2)
    path = tmp_path / "embeddings.f32"
    write_vectors(path, matrix)
    assert path.stat().st_size == 3 * 2 * 4
    raw = np.fromfile(path, dtype="<f4").reshape(3, 2)
    np.testing.assert_allclose(raw, [[0.6, 0.8], [1.0, 0.0], [0.0, -1.0]], rtol=1e-6)
    loaded = open_vectors(path, 3, 2)
    np.testing.assert_array_equal(np.asarray(loaded), raw)
    assert vector_problems(loaded) == []


def test_renormalizes_float64_input() -> None:
    matrix = normalize_rows([[1.0000001, 0.0]], 2)
    assert matrix.dtype == np.dtype("<f4")
    assert abs(float(np.linalg.norm(matrix[0])) - 1.0) < 1e-6


@pytest.mark.parametrize(
    "vectors", [[[1.0, float("nan")]], [[float("inf"), 0.0]], [[0.0, 0.0]], [[1.0, 0.0, 0.0]]]
)
def test_invalid_vectors_rejected(vectors: list[list[float]]) -> None:
    with pytest.raises(SnapshotError) as exc_info:
        normalize_rows(vectors, 2)
    assert exc_info.value.code == "EMBEDDING_INVALID_VECTOR"


def test_size_mismatch_rejected(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.f32"
    write_vectors(path, normalize_rows([[1.0, 0.0]], 2))
    with pytest.raises(SnapshotError) as exc_info:
        open_vectors(path, 2, 2)
    assert exc_info.value.code == "CHECKSUM_MISMATCH"


def test_problems_detect_nan_and_off_norm(tmp_path: Path) -> None:
    path = tmp_path / "e.f32"
    np.asarray([[1.0, 0.0], [np.nan, 0.0], [0.5, 0.5]], dtype="<f4").tofile(path)
    problems = vector_problems(open_vectors(path, 3, 2))
    assert any("non-finite" in p for p in problems)
    assert any("unit norm" in p for p in problems)
