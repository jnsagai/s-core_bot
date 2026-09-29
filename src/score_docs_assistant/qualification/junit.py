"""JUnit XML (pytest `--junitxml`, vitest `--reporter=junit`) → per-test outcomes (F008 R8)."""

from __future__ import annotations

import xml.etree.ElementTree as ET  # noqa: S405 — local files produced by our own test runs
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Outcome = Literal["passed", "failed", "skipped"]


@dataclass(frozen=True)
class TestOutcome:
    name: str  # "<classname>::<name>" (pytest node-like)
    outcome: Outcome


@dataclass(frozen=True)
class JUnitSummary:
    tests: list[TestOutcome]

    @property
    def counts(self) -> dict[str, int]:
        result = {"passed": 0, "failed": 0, "skipped": 0}
        for test in self.tests:
            result[test.outcome] += 1
        return result

    def matching(self, needle: str) -> list[TestOutcome]:
        return [t for t in self.tests if needle in t.name]


def parse_junit(path: Path) -> JUnitSummary:
    root = ET.parse(path).getroot()  # noqa: S314 — trusted local file
    outcomes: list[TestOutcome] = []
    for case in root.iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("failure") is not None or case.find("error") is not None:
            outcome: Outcome = "failed"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        outcomes.append(TestOutcome(name=name, outcome=outcome))
    return JUnitSummary(outcomes)
