"""Suite schema and composition (F008 FR-001, FR-002, SC-003)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from score_docs_assistant.qualification.suite import (
    MINIMUMS,
    SuiteCase,
    SuiteFile,
    composition_problems,
    freeze_status,
    load_suite,
)

REPO = Path(__file__).parent.parent.parent
SUITE = REPO / "eval" / "suite"
ANSWERED: dict[str, Any] = {
    "id": "x",
    "category": "onboarding_build",
    "question": "How do I build the docs?",
    "expected_status": "answered",
    "expected_facts": [{"fact": "Run bazel run //:docs."}],
    "evidence": [[{"source_id": "score-platform", "path": "docs/x.rst"}]],
}


def test_answerable_needs_facts_and_evidence() -> None:
    SuiteCase.model_validate(ANSWERED)
    with pytest.raises(ValidationError, match="expected facts"):
        SuiteCase.model_validate({**ANSWERED, "expected_facts": []})
    with pytest.raises(ValidationError, match="expected facts"):
        SuiteCase.model_validate({**ANSWERED, "evidence": []})


def test_human_review_needs_identity_and_regex_must_compile() -> None:
    with pytest.raises(ValidationError, match="reviewer and a date"):
        SuiteCase.model_validate({**ANSWERED, "review": {"status": "human_reviewed"}})
    with pytest.raises(ValidationError):
        SuiteCase.model_validate({**ANSWERED, "forbidden": ["re:(unclosed"]})


def _file(split: str, counts: dict[str, int], prefix: str) -> SuiteFile:
    cases = []
    for category, count in counts.items():
        for n in range(count):
            cases.append(
                {
                    "id": f"{prefix}-{category}-{n}",
                    "category": category,
                    "question": f"{prefix} {category} question {n}?",
                    "expected_status": "safe_handling",
                }
            )
    return SuiteFile.model_validate(
        {
            "schema_version": 1,
            "split": split,
            "review_status": "u",
            "written_against": {},
            "cases": cases,
        }
    )


def test_composition_rules() -> None:
    dev = {c: int(m * 0.6) for c, m in MINIMUMS.items()}
    held = {c: m - dev[c] for c, m in MINIMUMS.items()}
    assert composition_problems(_file("dev", dev, "d"), _file("heldout", held, "h")) == []
    skewed = dict(held, unsupported=held["unsupported"] - 3)
    dev_more = dict(dev, unsupported=dev["unsupported"] + 3)
    problems = composition_problems(_file("dev", dev_more, "d"), _file("heldout", skewed, "h"))
    assert any("not a stratified 40%" in p for p in problems)
    short = dict(dev, adversarial=dev["adversarial"] - 1)
    assert any(
        "adversarial: 19 < 20" in p
        for p in composition_problems(_file("dev", short, "d"), _file("heldout", held, "h"))
    )


def test_committed_suite_meets_master_spec() -> None:
    dev, _ = load_suite(SUITE / "dev.yaml")
    heldout, sha = load_suite(SUITE / "heldout.yaml")
    assert composition_problems(dev, heldout) == []
    assert (len(dev.cases), len(heldout.cases)) == (60, 40)
    assert not dev.human_reviewed and not heldout.human_reviewed  # agent-authored


def test_committed_heldout_matches_its_freeze() -> None:
    _, sha = load_suite(SUITE / "heldout.yaml")
    ok, reason = freeze_status(SUITE / "heldout.yaml", sha)
    assert ok, f"held-out suite {reason}; re-freeze only with `eval freeze --reason`"
