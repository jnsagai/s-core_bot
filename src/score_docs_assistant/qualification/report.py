"""Release report: every gate with its evidence kind and status, plus limitations (F008 FR-015).

The verdict is `ready` only when every required gate passes. A failed critical gate, or any
required gate that is failed, blocked or not run, makes it `blocked`, with the reasons listed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from score_docs_assistant import __version__
from score_docs_assistant.qualification.gates import (
    GateFile,
    GateResult,
    Identity,
    evaluate,
)
from score_docs_assistant.qualification.junit import JUnitSummary, parse_junit

_FORBID = ConfigDict(extra="forbid", frozen=True)
KIND_TITLES = {
    "deterministic": "Deterministic tests and checks",
    "real_model": "Real-model runs",
    "human": "Human reviews",
    "measurement": "Measurements",
}


class ReleaseReport(BaseModel):
    model_config = _FORBID

    created_at: datetime
    app_version: str
    identity: dict[str, str | None]
    verdict: str
    blocking: list[str]
    gates: list[GateResult]
    junit: dict[str, dict[str, int]]
    limitations: list[str]


def open_assumptions(path: Path) -> list[str]:
    """Rows of docs/ASSUMPTIONS.md whose status column says Open."""
    rows: list[str] = []
    if not path.is_file():
        return rows
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if (
            len(cells) >= 5
            and re.match(r"^A-\d{3}$", cells[0])
            and cells[-1].lower().startswith("open")
        ):
            rows.append(f"{cells[0]}: {cells[1][:220]}")
    return rows


def build_report(
    gates: GateFile,
    *,
    reports: Path,
    identity: Identity,
    traceability: list[str] | None,
    assumptions: Path,
) -> ReleaseReport:
    junit: list[tuple[str, JUnitSummary]] = []
    for pattern in ("pytest-*.xml", "vitest-*.xml"):
        files = sorted(reports.glob(pattern))
        if files:
            junit.append((files[-1].name, parse_junit(files[-1])))
    results = [
        evaluate(g, reports=reports, junit=junit, identity=identity, traceability=traceability)
        for g in gates.gates
    ]
    blocking = [
        f"{r.id}: {r.status} — {r.reason}" for r in results if r.required and r.status != "pass"
    ]
    critical = [r for r in results if r.critical and r.status == "fail"]
    verdict = "ready" if not blocking and not critical else "blocked"
    limitations = open_assumptions(assumptions) + [
        f"{r.id}: {r.reason}" for r in results if not r.required and r.status != "pass"
    ]
    return ReleaseReport(
        created_at=datetime.now(UTC),
        app_version=__version__,
        identity={
            "snapshot_id": identity.snapshot_id,
            "generation_digest": identity.generation_digest,
            "heldout_freeze": identity.freeze,
        },
        verdict=verdict,
        blocking=blocking,
        gates=results,
        junit={name: summary.counts for name, summary in junit},
        limitations=limitations,
    )


def _row(r: GateResult) -> str:
    evidence = r.evidence_file or "—"
    flag = " (critical)" if r.critical else ("" if r.required else " (not required)")
    return (
        f"| `{r.id}`{flag} | {r.title} | {r.target} | {r.value} | {r.status} | {r.kind} | "
        f"{evidence} | {r.reason} |"
    )


def to_markdown(report: ReleaseReport) -> str:
    lines = [
        "# Release report",
        "",
        f"Generated {report.created_at:%Y-%m-%d %H:%M UTC} by `release report` "
        f"(app {report.app_version}).",
        f"Active snapshot `{report.identity['snapshot_id']}`, locked generation model digest "
        f"`{(report.identity['generation_digest'] or '')[:12]}…`, held-out freeze "
        f"`{report.identity['heldout_freeze']}`.",
        "",
        f"## Verdict: **{report.verdict}**",
        "",
    ]
    if report.blocking:
        lines += ["Blocking items:", ""] + [f"- {b}" for b in report.blocking] + [""]
    lines += [
        "Statuses: `pass` (evidence meets the target), `fail`, `blocked` (a required input is",
        "missing, for example a human review), `not run` (no current evidence). No gate passes",
        "without an evidence file; nothing here is an approval.",
        "",
        "## Gates",
        "",
        "| Gate | Title | Target | Measured | Status | Evidence kind | Evidence | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        *[_row(r) for r in report.gates],
        "",
    ]
    for kind, title in KIND_TITLES.items():
        members = [r for r in report.gates if r.kind == kind]
        lines += [f"## {title}", ""]
        if kind == "deterministic" and report.junit:
            for name, counts in report.junit.items():
                lines.append(
                    f"- `{name}`: {counts['passed']} passed, {counts['failed']} failed, "
                    f"{counts['skipped']} skipped (skipped = not run)"
                )
            lines.append("")
        lines += [f"- `{r.id}` — {r.status}: {r.value} ({r.reason})" for r in members] or ["- none"]
        lines.append("")
    lines += ["## Unresolved limitations", ""]
    lines += [f"- {item}" for item in report.limitations] or ["- none recorded"]
    return "\n".join(lines) + "\n"
