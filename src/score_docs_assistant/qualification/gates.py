"""Declarative release gates evaluated against recorded evidence (F008 FR-015, research R8).

A gate never passes without an evidence file. Missing evidence → `not run`; human-judged gates
without an imported human review → `blocked`; development-labelled reports satisfy only gates that
accept them; evidence recorded against another snapshot, model or held-out freeze is stale.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.qualification.junit import JUnitSummary

Kind = Literal["deterministic", "real_model", "human", "measurement"]
Status = Literal["pass", "fail", "blocked", "not run"]
_FORBID = ConfigDict(extra="forbid", frozen=True)
_COMPARE = re.compile(r"^(>=|<=|==|!=|len ==|present)\s*(.*)$")


class Evidence(BaseModel):
    model_config = _FORBID

    report: str | None = None  # glob under the reports directory
    field: str | None = None  # dotted path; `[*]` over lists; `[key=value]` selects list items
    compare: str | None = None  # ">= 0.9", "== 0", "== pass", "len == 0", "present"
    accept_development: bool = False
    tests: list[str] = []  # substrings of JUnit test names; all must be present and passed
    check: Literal["traceability"] | None = None
    manual: str | None = None  # a recorded reason; the gate is blocked (or not run if deferred)
    deferred: bool = False

    @model_validator(mode="after")
    def _one(self) -> Evidence:
        kinds = [bool(self.report), bool(self.tests), bool(self.check), bool(self.manual)]
        if sum(kinds) != 1:
            raise ValueError("evidence needs exactly one of report, tests, check, manual")
        if self.report and not (self.field and self.compare and _COMPARE.match(self.compare)):
            raise ValueError("report evidence needs a field and a valid compare expression")
        return self


class GateSpec(BaseModel):
    model_config = _FORBID

    id: str
    title: str
    target: str
    kind: Kind
    critical: bool = False
    required: bool = True
    refs: list[str] = []  # master spec IDs (§13.3 metric names, AT-xx, budgets)
    evidence: Evidence


class GateFile(BaseModel):
    model_config = _FORBID

    schema_version: Literal[1]
    gates: list[GateSpec] = Field(min_length=1)


class GateResult(BaseModel):
    model_config = _FORBID

    id: str
    title: str
    target: str
    kind: Kind
    critical: bool
    required: bool
    refs: list[str]
    status: Status
    value: str
    evidence_file: str | None
    reason: str


@dataclass
class Identity:
    """The release being qualified: evidence from anything else is stale."""

    snapshot_id: str | None
    generation_digest: str | None
    freeze: str | None


def load_gates(path: Path) -> GateFile:
    try:
        return GateFile.model_validate(yaml.safe_load(path.read_text()))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigError([(str(path), f"invalid gate file: {exc}")]) from exc


def latest(reports: Path, pattern: str) -> Path | None:
    matches = sorted(p for p in reports.glob(pattern) if p.is_file())
    return matches[-1] if matches else None


def extract(data: Any, path: str) -> list[Any]:
    """Values at a dotted path; `[*]` fans out over a list, `[k=v]` filters list items."""
    values = [data]
    for part in re.findall(r"[^.\[\]]+|\[[^\]]*\]", path):
        nxt: list[Any] = []
        for value in values:
            if part == "[*]":
                nxt.extend(value if isinstance(value, list) else [])
            elif part.startswith("["):
                key, _, wanted = part[1:-1].partition("=")
                nxt.extend(
                    v for v in (value or []) if isinstance(v, dict) and str(v.get(key)) == wanted
                )
            elif isinstance(value, dict) and part in value:
                nxt.append(value[part])
        values = nxt
    return values


def compare(values: list[Any], expression: str) -> tuple[bool, str]:
    match = _COMPARE.match(expression)
    assert match is not None
    op, operand = match.group(1), match.group(2).strip()
    if op == "present":
        ok = bool(values) and all(v not in (None, "", "not available") for v in values)
        return ok, "present" if ok else "not available"
    if op == "len ==":
        lengths = [len(v) if isinstance(v, list | dict) else -1 for v in values]
        return bool(values) and all(n == int(operand) for n in lengths), f"len {lengths}"
    if not values:
        return False, "no value"

    def one(v: Any) -> bool:
        if isinstance(v, bool) or not isinstance(v, int | float):
            text = str(v).lower()
            return (text == operand.lower()) if op == "==" else (text != operand.lower())
        number = float(operand)
        return {">=": v >= number, "<=": v <= number, "==": v == number, "!=": v != number}[op]

    shown = ", ".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in values)
    return all(one(v) for v in values), shown


def _stale(data: dict[str, Any], identity: Identity) -> str | None:
    snapshot = data.get("snapshot_id")
    if (
        identity.snapshot_id
        and isinstance(snapshot, str)
        and snapshot
        and snapshot != identity.snapshot_id
    ):
        return f"snapshot {snapshot} is not the active {identity.snapshot_id}"
    model = data.get("model")
    digest = model.get("digest") if isinstance(model, dict) else None
    if (
        identity.generation_digest
        and isinstance(digest, str)
        and digest
        and digest != identity.generation_digest
    ):
        return f"model digest {digest[:12]}… is not the locked {identity.generation_digest[:12]}…"
    freeze = data.get("freeze")
    if (
        identity.freeze
        and data.get("split") == "heldout"
        and isinstance(freeze, str)
        and freeze != identity.freeze
    ):
        return f"held-out freeze '{freeze}' is not the current '{identity.freeze}'"
    return None


def evaluate(
    spec: GateSpec,
    *,
    reports: Path,
    junit: list[tuple[str, JUnitSummary]],
    identity: Identity,
    traceability: list[str] | None,
) -> GateResult:
    ev = spec.evidence

    def result(status: Status, value: str, evidence: str | None, reason: str) -> GateResult:
        return GateResult(
            id=spec.id,
            title=spec.title,
            target=spec.target,
            kind=spec.kind,
            critical=spec.critical,
            required=spec.required,
            refs=spec.refs,
            status=status,
            value=value,
            evidence_file=evidence,
            reason=reason,
        )

    if ev.manual:
        return result("not run" if ev.deferred else "blocked", "—", None, ev.manual)
    if ev.check == "traceability":
        if traceability is None:
            return result("not run", "—", None, "traceability check not executed")
        ok = not traceability
        return result(
            "pass" if ok else "fail",
            "complete" if ok else f"{len(traceability)} problem(s)",
            "docs/TRACEABILITY.md",
            "every local requirement mapped" if ok else "; ".join(traceability[:5]),
        )
    if ev.tests:
        if not junit:
            return result("not run", "—", None, "no JUnit results recorded")
        found: dict[str, str] = {}
        files: set[str] = set()
        for needle in ev.tests:
            for name, summary in junit:
                matches = summary.matching(needle)
                if matches:
                    files.add(name)
                    outcomes = {m.outcome for m in matches}
                    found[needle] = (
                        "failed"
                        if "failed" in outcomes
                        else ("skipped" if outcomes == {"skipped"} else "passed")
                    )
                    break
        missing = [n for n in ev.tests if n not in found]
        failed = [n for n, o in found.items() if o == "failed"]
        skipped = [n for n, o in found.items() if o == "skipped"]
        value = f"{sum(o == 'passed' for o in found.values())}/{len(ev.tests)} tests passed"
        evidence = ", ".join(sorted(files)) or None
        if failed:
            return result("fail", value, evidence, f"failed: {failed}")
        if missing or skipped:
            return result("not run", value, evidence, f"missing: {missing} skipped: {skipped}")
        return result("pass", value, evidence, "all listed tests passed")
    assert ev.report and ev.field and ev.compare
    path = latest(reports, ev.report)
    if path is None:
        if spec.kind == "human":
            return result("blocked", "—", None, "awaiting human review (no imported review sheet)")
        return result("not run", "—", None, f"no report matching {ev.report}")
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return result("fail", "—", path.name, f"unreadable evidence: {exc}")
    stale = _stale(data, identity)
    if stale:
        return result("not run", "—", path.name, f"stale evidence: {stale}")
    ok, shown = compare(extract(data, ev.field), ev.compare)
    labels = data.get("labels") or []
    if "development measurement" in labels and not ev.accept_development:
        return result(
            "blocked", shown, path.name, "suite cases unreviewed (development measurement)"
        )
    return result("pass" if ok else "fail", shown, path.name, f"{ev.field} {ev.compare}")
