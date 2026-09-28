"""Masked exact cosine top-k (FR-008, research R3)."""

from __future__ import annotations

import numpy as np

from score_docs_assistant.retrieval.semantic import top_k


def test_top_k_orders_by_cosine_and_returns_rowids() -> None:
    matrix = np.array([[1, 0], [0, 1], [0.8, 0.6]], dtype=np.float32)
    assert top_k(matrix, np.array([1, 0], dtype=np.float32), None, 2) == [1, 3]


def test_mask_applied_before_selection() -> None:
    matrix = np.array([[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]], dtype=np.float32)
    mask = np.array([False, False, True, True])
    assert top_k(matrix, np.array([1, 0], dtype=np.float32), mask, 2) == [4, 3]


def test_ties_broken_by_row() -> None:
    matrix = np.array([[1, 0], [1, 0], [1, 0]], dtype=np.float32)
    assert top_k(matrix, np.array([1, 0], dtype=np.float32), None, 3) == [1, 2, 3]


def test_empty_mask_and_k_larger_than_rows() -> None:
    matrix = np.array([[1, 0], [0, 1]], dtype=np.float32)
    assert top_k(matrix, np.array([1, 0], dtype=np.float32), np.array([False, False]), 5) == []
    assert top_k(matrix, np.array([1, 0], dtype=np.float32), None, 5) == [1, 2]
