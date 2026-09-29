"""Release report assembly and verdict (F008 FR-015, US1)."""

from __future__ import annotations

import json
from pathlib import Path

from score_docs_assistant.qualification.gates import Evidence, GateFile, GateSpec, Identity
from score_docs_assistant.qualification.report import build_report, open_assumptions, to_markdown

ID = Identity(snapshot_id="S1", generation_digest="d" * 64, freeze="frozen")


def gates(*specs: GateSpec) -> GateFile:
    return GateFile(schema_version=1, gates=list(specs))


def spec(
    gid: str, kind: str = "real_model", critical: bool = False, required: bool = True, **ev
) -> GateSpec:  # type: ignore[no-untyped-def]
    return GateSpec(
        id=gid,
        title=gid,
        target="t",
        kind=kind,
        critical=critical,
        required=required,
        evidence=Evidence(**ev),
    )  # type: ignore[arg-type]


def test_ready_only_when_every_required_gate_passes(tmp_path: Path) -> None:
    (tmp_path / "a-1.json").write_text(json.dumps({"v": 1}))
    ready = build_report(
        gates(
            spec("a", report="a-*.json", field="v", compare="== 1"),
            spec("pub", manual="F010", deferred=True, required=False),
        ),
        reports=tmp_path,
        identity=ID,
        traceability=[],
        assumptions=tmp_path / "none.md",
    )
    assert ready.verdict == "ready" and ready.blocking == []
    assert any("pub" in item for item in ready.limitations)


def test_blocked_by_human_gate_and_missing_evidence(tmp_path: Path) -> None:
    report = build_report(
        gates(
            spec("human", kind="human", report="human-review-*.json", field="v", compare=">= 1"),
            spec("absent", report="none-*.json", field="v", compare="== 1"),
        ),
        reports=tmp_path,
        identity=ID,
        traceability=[],
        assumptions=tmp_path / "none.md",
    )
    assert report.verdict == "blocked"
    assert [g.status for g in report.gates] == ["blocked", "not run"]


def test_critical_failure_blocks_even_if_not_required(tmp_path: Path) -> None:
    (tmp_path / "adv-1.json").write_text(json.dumps({"failures": 1}))
    report = build_report(
        gates(
            spec(
                "adv",
                critical=True,
                required=False,
                report="adv-*.json",
                field="failures",
                compare="== 0",
            )
        ),
        reports=tmp_path,
        identity=ID,
        traceability=[],
        assumptions=tmp_path / "none.md",
    )
    assert report.verdict == "blocked"


def test_markdown_sections_and_open_assumptions(tmp_path: Path) -> None:
    assumptions = tmp_path / "A.md"
    assumptions.write_text(
        "| ID | Assumption | Source | Owner | Status |\n| --- | --- | --- | --- | --- |\n"
        "| A-001 | Closed one | x | y | Resolved |\n| A-002 | Still open thing | x | y | Open |\n"
    )
    assert open_assumptions(assumptions) == ["A-002: Still open thing"]
    report = build_report(
        gates(spec("d", kind="deterministic", check="traceability")),
        reports=tmp_path,
        identity=ID,
        traceability=["LOC-009: no row"],
        assumptions=assumptions,
    )
    md = to_markdown(report)
    for heading in (
        "## Verdict: **blocked**",
        "## Gates",
        "## Deterministic tests and checks",
        "## Real-model runs",
        "## Human reviews",
        "## Measurements",
        "## Unresolved limitations",
    ):
        assert heading in md
    assert "A-002: Still open thing" in md and "nothing here is an approval" in md
    assert report.gates[0].status == "fail"
