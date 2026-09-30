"""Gate evaluation — every status path (F008 FR-015, SC-001, SC-002)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from score_docs_assistant.qualification.gates import (
    Evidence,
    GateSpec,
    Identity,
    compare,
    evaluate,
    extract,
    load_gates,
)
from score_docs_assistant.qualification.junit import CaseOutcome, JUnitSummary

REPO = Path(__file__).parent.parent.parent
ID = Identity(snapshot_id="S1", generation_digest="d" * 64, freeze="frozen on 2026-09-29")


def gate(kind: str = "real_model", **evidence: Any) -> GateSpec:
    return GateSpec(id="g", title="t", target="x", kind=kind, evidence=Evidence(**evidence))  # type: ignore[arg-type]


def write(reports: Path, name: str, data: dict[str, Any]) -> None:
    reports.mkdir(exist_ok=True)
    (reports / name).write_text(json.dumps(data))


def run(spec: GateSpec, reports: Path, junit: list[tuple[str, JUnitSummary]] | None = None):  # type: ignore[no-untyped-def]
    return evaluate(spec, reports=reports, junit=junit or [], identity=ID, traceability=[])


def test_extract_and_compare() -> None:
    data = {
        "runs": [{"m": {"value": 0.95}}, {"m": {"value": 0.91}}],
        "b": [{"name": "x", "s": "pass"}],
    }
    assert extract(data, "runs[*].m.value") == [0.95, 0.91]
    assert extract(data, "b[name=x].s") == ["pass"]
    assert compare([0.95, 0.91], ">= 0.90")[0] and not compare([0.95, 0.89], ">= 0.90")[0]
    assert compare(["pass"], "== pass")[0] and compare([[]], "len == 0")[0]
    assert not compare([], ">= 0.9")[0] and not compare(["not available"], "present")[0]
    assert compare([True], "== true")[0]


def test_missing_report_is_not_run_and_human_is_blocked(tmp_path: Path) -> None:
    spec = gate(report="x-*.json", field="v", compare="== 1")
    assert run(spec, tmp_path).status == "not run"
    human = gate("human", report="human-review-*.json", field="v", compare=">= 0.95")
    result = run(human, tmp_path)
    assert result.status == "blocked" and "awaiting human review" in result.reason


def test_pass_fail_and_development_label(tmp_path: Path) -> None:
    write(tmp_path, "x-1.json", {"v": 1, "labels": []})
    assert run(gate(report="x-*.json", field="v", compare="== 1"), tmp_path).status == "pass"
    write(tmp_path, "x-2.json", {"v": 0, "labels": []})  # latest file wins
    assert run(gate(report="x-*.json", field="v", compare="== 1"), tmp_path).status == "fail"
    write(tmp_path, "y-1.json", {"v": 1, "labels": ["development measurement"]})
    dev = run(gate(report="y-*.json", field="v", compare="== 1"), tmp_path)
    assert dev.status == "blocked" and "unreviewed" in dev.reason
    ok = run(gate(report="y-*.json", field="v", compare="== 1", accept_development=True), tmp_path)
    assert ok.status == "pass"


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ({"snapshot_id": "OTHER", "v": 1}, "snapshot OTHER"),
        ({"model": {"digest": "e" * 64}, "v": 1}, "model digest"),
        ({"split": "heldout", "freeze": "frozen on 2020-01-01", "v": 1}, "freeze"),
    ],
)
def test_stale_evidence_is_not_run(tmp_path: Path, data: dict[str, Any], fragment: str) -> None:
    write(tmp_path, "z-1.json", data)
    result = run(gate(report="z-*.json", field="v", compare="== 1"), tmp_path)
    assert result.status == "not run" and fragment in result.reason


def test_tests_evidence(tmp_path: Path) -> None:
    summary = JUnitSummary(
        [
            CaseOutcome("tests.a::test_one", "passed"),
            CaseOutcome("tests.a::test_two", "failed"),
            CaseOutcome("tests.b::test_real", "skipped"),
        ]
    )
    junit = [("pytest-1.xml", summary)]
    assert run(gate("deterministic", tests=["test_one"]), tmp_path, junit).status == "pass"
    assert (
        run(gate("deterministic", tests=["test_one", "test_two"]), tmp_path, junit).status == "fail"
    )
    assert run(gate("deterministic", tests=["test_real"]), tmp_path, junit).status == "not run"
    assert run(gate("deterministic", tests=["test_absent"]), tmp_path, junit).status == "not run"
    assert run(gate("deterministic", tests=["test_one"]), tmp_path, []).status == "not run"


def test_manual_and_deferred(tmp_path: Path) -> None:
    assert run(gate("human", manual="awaiting review"), tmp_path).status == "blocked"
    assert run(gate(manual="F010", deferred=True), tmp_path).status == "not run"


def test_evidence_needs_exactly_one_kind() -> None:
    with pytest.raises(ValueError):
        Evidence(report="x", tests=["y"], field="v", compare="== 1")
    with pytest.raises(ValueError):
        Evidence(report="x")


def test_committed_gate_file_covers_master_thresholds_budgets_and_scenarios() -> None:
    gates = load_gates(REPO / "eval" / "release-gates.yaml")
    refs = " ".join(r for g in gates.gates for r in g.refs)
    for metric in (
        "recall@10",
        "exact-ID",
        "citation integrity",
        "factual support precision",
        "required-fact coverage",
        "safe handling",
        "false abstention",
        "snapshot isolation",
        "injection resistance",
        "offline operation",
        "operational recovery",
    ):
        assert f"§13.3 {metric}" in refs, metric
    assert refs.count("§13.4") >= 6
    covered = set(re.findall(r"AT-\d{2}", refs))
    assert {f"AT-{n:02d}" for n in range(1, 19)} <= covered
    assert any(not g.required and "AT-19" in g.refs for g in gates.gates)


def test_gate_file_covers_f009_deployment_requirements() -> None:
    gates = load_gates(REPO / "eval" / "release-gates.yaml")
    refs = " ".join(r for g in gates.gates for r in g.refs)
    for ref in (
        "LOC-004",
        "OPS-001",
        "OPS-003",
        "OPS-005",
        "§17.2",
        "§18.3 fresh install",
        "AT-16",
    ):
        assert ref in refs, ref


def test_blanket_review_is_labelled_and_accepts_its_own_run_series(tmp_path: Path) -> None:
    human = gate("human", report="human-review-*.json", field="v", compare=">= 0.95")
    write(
        tmp_path,
        "human-review-1.json",
        {
            "v": 1.0,
            "attestation": "blanket",
            "reviewer": "owner",
            "reviewed_on": "2026-09-30",
            "statement": "I reviewed and accept.",
            "run_reference": {"file": "suite-run1.json"},
        },
    )
    result = run(human, tmp_path)
    assert result.status == "pass" and "blanket owner acceptance, not per-claim" in result.reason

    held = gate(
        report="suite-*-combined.json", field="v", compare="== 1", accepted_by="human-review-*.json"
    )
    write(
        tmp_path,
        "suite-a-combined.json",
        {"v": 1, "labels": ["development measurement"], "run_files": ["other.json"]},
    )
    assert run(held, tmp_path).status == "blocked"  # the review is of another run series
    write(
        tmp_path,
        "suite-b-combined.json",
        {"v": 1, "labels": ["development measurement"], "run_files": ["suite-run1.json"]},
    )
    accepted = run(held, tmp_path)
    assert accepted.status == "pass" and "blanket owner acceptance" in accepted.reason
