#!/usr/bin/env python3
"""Traceability completeness check (F008 FR-016, research R9).

Every local requirement in docs/PROJECT_SPEC.md must be covered exactly once in
docs/TRACEABILITY.md, with a status. Paths named in the Implementation and Tests columns must
exist, and public-profile (PUB) requirements must be marked deferred. Exit 1 lists the problems.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ("LOC", "SRC", "RET", "ANS", "UX", "SEC", "OPS")
REQ_ROW = re.compile(r"^\|\s*((?:LOC|SRC|RET|ANS|UX|SEC|OPS|PUB)-\d{3})\s*\|")
RANGE = re.compile(r"^([A-Z]+)-(\d{3})\s*[–-]\s*\1-(\d{3})$")
BACKTICK = re.compile(r"`([^`]+)`")
PATH_SUFFIXES = (".py", ".ts", ".tsx", ".md", ".yaml", ".yml", ".json", ".sh", ".mjs", ".toml")
SEARCH_ROOTS = ("", "src/score_docs_assistant", "frontend")


def spec_requirements(spec_text: str) -> list[str]:
    return sorted({m.group(1) for line in spec_text.splitlines() if (m := REQ_ROW.match(line))})


def expand(cell: str) -> list[str]:
    cell = cell.strip()
    if m := RANGE.match(cell):
        prefix, start, end = m.group(1), int(m.group(2)), int(m.group(3))
        return [f"{prefix}-{n:03d}" for n in range(start, end + 1)]
    return [cell]


def path_exists(token: str, root: Path) -> bool:
    for base in SEARCH_ROOTS:
        candidate = root / base / token
        if any(ch in token for ch in "*?"):
            if list((root / base).glob(token)):
                return True
        elif candidate.exists():
            return True
    return False


def looks_like_path(token: str) -> bool:
    token = token.strip()
    if " " in token or token.startswith(("-", "http")) or "=" in token or ":" in token:
        return False
    return "/" in token or token.endswith(PATH_SUFFIXES)


def check(spec_text: str, trace_text: str, root: Path) -> list[str]:
    problems: list[str] = []
    required = spec_requirements(spec_text)
    seen: dict[str, int] = {}
    rows = [
        line
        for line in trace_text.splitlines()
        if line.startswith("| ") and not line.startswith("| Req ") and not line.startswith("| ---")
    ]
    for line in rows:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            problems.append(f"malformed row: {line[:60]}")
            continue
        ids = expand(cells[0])
        status = cells[-1]
        for req in ids:
            seen[req] = seen.get(req, 0) + 1
        if not status:
            problems.append(f"{cells[0]}: no status")
        if any(req.startswith("PUB") for req in ids):
            if "deferred" not in status.lower():
                problems.append(f"{cells[0]}: public-profile requirements must be marked deferred")
            continue
        for column in (cells[4], cells[5]):
            for token in BACKTICK.findall(column):
                token = token.split(" (")[0].strip()
                if looks_like_path(token) and not path_exists(token, root):
                    problems.append(f"{cells[0]}: path does not exist: {token}")
    for req in required:
        count = seen.get(req, 0)
        if req.split("-")[0] in LOCAL or req.startswith("PUB"):
            if count == 0:
                problems.append(f"{req}: no traceability row")
            elif count > 1:
                problems.append(f"{req}: covered by {count} rows")
    for req in seen:
        if req not in required:
            problems.append(f"{req}: in TRACEABILITY but not in the master spec")
    return problems


def main() -> int:
    problems = check(
        (ROOT / "docs" / "PROJECT_SPEC.md").read_text(),
        (ROOT / "docs" / "TRACEABILITY.md").read_text(),
        ROOT,
    )
    for problem in problems:
        print(f"TRACEABILITY: {problem}")
    if not problems:
        print("Traceability check passed: every local requirement is mapped; PUB deferred.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
