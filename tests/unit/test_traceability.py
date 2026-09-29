"""Traceability completeness checker (F008 FR-016, SC-007)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
spec = importlib.util.spec_from_file_location(
    "check_traceability", REPO / "scripts" / "check_traceability.py"
)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

SPEC = """
| LOC-001 | text | A |
| LOC-002 | text | A |
| UX-001 | text | A |
| UX-002 | text | A |
| PUB-001 | text | A |
"""
HEADER = (
    "| Req | Owner | FR | Tasks | Impl | Tests | Evidence | Status |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


def row(req: str, impl: str = "`scripts/check_traceability.py`", status: str = "verified") -> str:
    return (
        f"| {req} | F1 | FR-1 | T1 | {impl} | `tests/unit/test_traceability.py` | ev | {status} |\n"
    )


def test_complete_mapping_passes(tmp_path: Path) -> None:
    trace = (
        HEADER
        + row("LOC-001")
        + row("LOC-002")
        + row("UX-001 – UX-002")
        + row("PUB-001", status="open (deferred)")
    )
    assert checker.check(SPEC, trace, REPO) == []


def test_problems_are_reported() -> None:
    trace = (
        HEADER
        + row("LOC-001", impl="`src/does/not/exist.py`")
        + row("UX-001 – UX-002")
        + row("UX-002")
        + row("PUB-001", status="open")
        + row("SEC-009")
        + row("LOC-001", status="")
    )
    problems = "\n".join(checker.check(SPEC, trace, REPO))
    assert "path does not exist: src/does/not/exist.py" in problems
    assert "LOC-002: no traceability row" in problems
    assert "UX-002: covered by 2 rows" in problems
    assert "LOC-001: covered by 2 rows" in problems
    assert "PUB-001" in problems and "deferred" in problems
    assert "SEC-009: in TRACEABILITY but not in the master spec" in problems
    assert "no status" in problems


def test_real_repository_is_complete() -> None:
    assert checker.main() == 0
