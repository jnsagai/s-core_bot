"""The 100-case evaluation suite and its held-out freeze (F008 FR-001–FR-003, research R1, R2).

Case authoring status is recorded per case; only a person can set `human_reviewed`, and it needs a
reviewer and a date. The held-out file is frozen by a committed hash manifest before its first run.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.retrieval.evaluation import Locator

Category = Literal[
    "onboarding_build",
    "architecture_interfaces",
    "process_work_products",
    "requirements_templates",
    "unsupported",
    "adversarial",
]
ExpectedStatus = Literal[
    "answered", "partial", "insufficient_evidence", "clarification_needed", "safe_handling"
]
Split = Literal["dev", "heldout"]
MINIMUMS: dict[str, int] = {
    "onboarding_build": 15,
    "architecture_interfaces": 15,
    "process_work_products": 15,
    "requirements_templates": 15,
    "unsupported": 20,
    "adversarial": 20,
}
TOTAL_CASES = 100
HELDOUT_SHARE = 0.4
ANSWERABLE = ("answered", "partial")
_FORBID = ConfigDict(extra="forbid", frozen=True)


class ExpectedFact(BaseModel):
    model_config = _FORBID

    fact: str = Field(min_length=1)
    variants: list[str] = []
    required: bool = True


class CaseReview(BaseModel):
    model_config = _FORBID

    status: Literal["unreviewed", "agent_review", "human_reviewed"] = "unreviewed"
    reviewer: str | None = None
    date: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _human_needs_identity(self) -> CaseReview:
        if self.status == "human_reviewed" and not (self.reviewer and self.date):
            raise ValueError("human_reviewed needs a reviewer and a date")
        return self


class SuiteCase(BaseModel):
    model_config = _FORBID

    id: str = Field(min_length=1)
    category: Category
    tags: list[str] = []
    question: str = Field(min_length=1, max_length=4000)
    expected_status: ExpectedStatus
    expected_facts: list[ExpectedFact] = []
    evidence: list[list[Locator]] = []
    forbidden: list[str] = []
    review: CaseReview = Field(default_factory=CaseReview)

    @model_validator(mode="after")
    def _answerable_needs_facts(self) -> SuiteCase:
        if self.expected_status in ANSWERABLE and not (self.expected_facts and self.evidence):
            raise ValueError("answered/partial cases need expected facts and gold evidence")
        if any(not group for group in self.evidence):
            raise ValueError("every evidence group needs at least one locator")
        for pattern in self.forbidden:
            if pattern.startswith("re:"):
                try:
                    re.compile(pattern[3:])
                except re.error as exc:
                    raise ValueError(f"forbidden pattern {pattern!r} is not a valid regex") from exc
        return self

    @property
    def answerable(self) -> bool:
        return self.expected_status in ANSWERABLE


class SuiteFile(BaseModel):
    model_config = _FORBID

    schema_version: Literal[1]
    split: Split
    review_status: str = Field(min_length=1)
    written_against: dict[str, str]
    cases: list[SuiteCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> SuiteFile:
        ids = [c.id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique")
        return self

    @property
    def human_reviewed(self) -> bool:
        return all(c.review.status == "human_reviewed" for c in self.cases)


def load_suite(path: Path) -> tuple[SuiteFile, str]:
    try:
        raw = path.read_bytes()
        return SuiteFile.model_validate(yaml.safe_load(raw)), hashlib.sha256(raw).hexdigest()
    except OSError as exc:
        raise ConfigError([(str(path), f"cannot read suite file: {exc}")]) from exc
    except yaml.YAMLError as exc:
        raise ConfigError([(str(path), f"invalid YAML: {exc}")]) from exc
    except ValidationError as exc:
        raise ConfigError(
            [(f"{path}:{'.'.join(str(p) for p in e['loc'])}", e["msg"]) for e in exc.errors()]
        ) from exc


def composition_problems(dev: SuiteFile, heldout: SuiteFile) -> list[str]:
    """Unmet master §13.2 composition rules for the dev/held-out pair (empty when satisfied)."""
    problems: list[str] = []
    if dev.split != "dev" or heldout.split != "heldout":
        problems.append("files must be split dev and heldout")
    cases = [*dev.cases, *heldout.cases]
    if len(cases) != TOTAL_CASES:
        problems.append(f"{len(cases)} cases, expected {TOTAL_CASES}")
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        problems.append("case ids repeat across the two files")
    questions = [" ".join(c.question.lower().split()) for c in cases]
    if len(questions) != len(set(questions)):
        problems.append("a question appears twice")
    for category, minimum in MINIMUMS.items():
        total = sum(1 for c in cases if c.category == category)
        held = sum(1 for c in heldout.cases if c.category == category)
        if total < minimum:
            problems.append(f"{category}: {total} < {minimum}")
        expected_held = total * HELDOUT_SHARE
        if abs(held - expected_held) > 1:
            problems.append(f"{category}: {held} held-out of {total} is not a stratified 40%")
    return problems


class FreezeManifest(BaseModel):
    model_config = _FORBID

    file: str
    sha256: str
    cases: int
    frozen_on: str
    reason: str = Field(min_length=1)
    previous_sha256: str | None = None


def manifest_path(suite_path: Path) -> Path:
    return suite_path.with_name(suite_path.stem + ".freeze.json")


def freeze(suite_path: Path, reason: str, today: date | None = None) -> FreezeManifest:
    suite, sha = load_suite(suite_path)
    path = manifest_path(suite_path)
    previous = read_manifest(suite_path)
    manifest = FreezeManifest(
        file=suite_path.name,
        sha256=sha,
        cases=len(suite.cases),
        frozen_on=(today or date.today()).isoformat(),
        reason=reason,
        previous_sha256=previous.sha256 if previous and previous.sha256 != sha else None,
    )
    path.write_text(json.dumps(manifest.model_dump(), indent=2) + "\n")
    return manifest


def read_manifest(suite_path: Path) -> FreezeManifest | None:
    path = manifest_path(suite_path)
    if not path.is_file():
        return None
    try:
        return FreezeManifest.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise ConfigError([(str(path), f"invalid freeze manifest: {exc}")]) from exc


def freeze_status(suite_path: Path, sha: str) -> tuple[bool, str]:
    """(ok, reason): the file matches its manifest."""
    manifest = read_manifest(suite_path)
    if manifest is None:
        return False, "not frozen (no manifest)"
    if manifest.sha256 != sha:
        return False, f"changed since it was frozen on {manifest.frozen_on}"
    return True, f"frozen on {manifest.frozen_on}"
