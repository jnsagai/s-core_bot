"""Held-out freeze manifest (F008 FR-003, research R2)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from score_docs_assistant.qualification.suite import (
    freeze,
    freeze_status,
    load_suite,
    manifest_path,
    read_manifest,
)

CASE = {
    "id": "ho-001",
    "category": "unsupported",
    "question": "What is the capital of France?",
    "expected_status": "safe_handling",
}


def _write(path: Path, question: str = CASE["question"]) -> Path:
    data = {
        "schema_version": 1,
        "split": "heldout",
        "review_status": "unreviewed",
        "written_against": {},
        "cases": [{**CASE, "question": question}],
    }
    path.write_text(yaml.safe_dump(data))
    return path


def test_freeze_then_detect_change(tmp_path: Path) -> None:
    suite = _write(tmp_path / "heldout.yaml")
    _, sha = load_suite(suite)
    assert freeze_status(suite, sha) == (False, "not frozen (no manifest)")
    manifest = freeze(suite, "initial freeze", today=date(2026, 9, 29))
    assert manifest_path(suite).name == "heldout.freeze.json"
    assert (manifest.sha256, manifest.cases, manifest.previous_sha256) == (sha, 1, None)
    assert freeze_status(suite, sha) == (True, "frozen on 2026-09-29")
    _write(suite, "What is the capital of Spain?")
    _, changed = load_suite(suite)
    ok, reason = freeze_status(suite, changed)
    assert not ok and "changed since it was frozen" in reason


def test_refreeze_keeps_previous_hash(tmp_path: Path) -> None:
    suite = _write(tmp_path / "heldout.yaml")
    first = freeze(suite, "initial")
    _write(suite, "Corrected question?")
    second = freeze(suite, "reviewer corrected a question")
    assert second.previous_sha256 == first.sha256
    manifest = read_manifest(suite)
    assert manifest is not None and manifest.reason == "reviewer corrected a question"
