"""`score-assistant compare` (specs/007-version-comparison/contracts/cli.md)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

import typer

from score_docs_assistant.cli.ask import build_answer_service
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.cli.search_support import _config, handle_search_errors
from score_docs_assistant.comparison.service import ComparisonService
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.answers import AnswerEnvelope, Citation
from score_docs_assistant.domain.comparison import (
    ComparisonRequest,
    ComparisonResult,
    Difference,
    SnapshotDiff,
)
from score_docs_assistant.domain.errors import GenerationError

NO_RELEASE_LABEL = "No release label: per-source revisions identify each snapshot."
RELATION_TEXT = {
    "same": "same",
    "different": "different",
    "left_only": "left only",
    "right_only": "right only",
}


def build_comparison_service(config: AppConfig) -> ComparisonService:
    answers = build_answer_service(config)
    return ComparisonService(config=config, search=answers._search, answers=answers)  # noqa: SLF001


def _revision(revision: str | None, status: str | None) -> str:
    return "—" if revision is None else f"{revision[:7]}… ({status})"


def render_diff(diff: SnapshotDiff) -> list[str]:
    lines = [f"left  {diff.left_snapshot_id}   right {diff.right_snapshot_id}", "sources:"]
    for row in diff.sources:
        lines.append(
            f"  {row.source_id}  {RELATION_TEXT[row.relation]}  "
            f"{_revision(row.left_revision, row.left_revision_status)} → "
            f"{_revision(row.right_revision, row.right_revision_status)}"
        )
    for p in diff.processing:
        lines.append(f"processing: {p.field}  {p.left} → {p.right}")
    lines.append(NO_RELEASE_LABEL)
    lines.extend(f"warning: {w}" for w in diff.warnings)
    return lines


def _side(label: str, envelope: AnswerEnvelope, evidence: list[Citation]) -> list[str]:
    """Side claims with their E-IDs mapped to the comparison's L/R evidence (same chunk)."""
    by_chunk = {c.chunk_id: c.evidence_id for c in evidence}
    mapped = {
        c.evidence_id: by_chunk.get(c.chunk_id, f"{label.lower()} {c.evidence_id}")
        for c in envelope.citations
    }
    lines = [f"{label} (status {envelope.status})"]
    for claim in envelope.claims:
        marker = "" if claim.kind == "documented" else f"({claim.kind}) "
        refs = " ".join(f"[{mapped.get(e, e)}]" for e in claim.evidence_ids)
        lines.append(f"- {marker}{claim.text} {refs}".rstrip())
    return lines


def _difference(d: Difference) -> str:
    refs = " ".join(f"[{e}]" for e in [*d.left_evidence_ids, *d.right_evidence_ids])
    if d.type == "not_established":
        head = f"not established ({d.missing_side} side missing; {d.coverage_reason})"
    else:
        head = d.type
    return f"- {head}: {d.statement} {refs}".rstrip()


def _citation(c: Citation, show_evidence: bool) -> list[str]:
    span = f":{c.line_start}-{c.line_end}" if c.line_start is not None else ""
    link = f"  {c.immutable_url}" if c.immutable_url else ""
    lines = [f"[{c.evidence_id}] {c.source_id}  {c.path}{span}  ({c.revision_status}){link}"]
    if show_evidence:
        lines.extend(f"     | {line}" for line in c.excerpt.splitlines())
    return lines


def render(result: ComparisonResult, *, show_evidence: bool) -> str:
    model = f"{result.model.name} ({result.model.digest[:12]})" if result.model else "not used"
    lines = render_diff(result.snapshots)
    lines[0] += f"   model {model}"
    lines += _side("LEFT", result.left, result.evidence.left)
    lines += _side("RIGHT", result.right, result.evidence.right)
    lines.append("differences:")
    lines += [_difference(d) for d in result.differences] or ["- (none)"]
    lines.append("evidence:")
    for citation in [*result.evidence.left, *result.evidence.right]:
        lines += _citation(citation, show_evidence)
    return "\n".join(lines)


@cli_app.command("compare")
@handle_common_errors
@handle_search_errors
def compare_command(
    ctx: typer.Context,
    question: Annotated[str, typer.Argument(help="Your question.")],
    left: Annotated[str, typer.Option("--left", help="Left snapshot ID.")],
    right: Annotated[str, typer.Option("--right", help="Right snapshot ID.")],
    json_output: Annotated[bool, typer.Option("--json", help="Print the comparison JSON.")] = False,
    show_evidence: Annotated[
        bool, typer.Option("--show-evidence", help="Also print each excerpt.")
    ] = False,
) -> None:
    """Compares how two snapshots answer a question with the local model; evidence stays separate
    per snapshot (no downloads)."""
    service = build_comparison_service(_config(ctx))
    try:
        request = ComparisonRequest(
            question=question, left_snapshot_id=left, right_snapshot_id=right
        )
        result = asyncio.run(service.compare(request, request_id=uuid.uuid4().hex))
    except ValueError as exc:
        typer.echo(f"REQUEST_INVALID: {exc}", err=True)
        raise typer.Exit(code=2) from None
    except GenerationError as exc:
        typer.echo(f"{exc.code}: {exc.message}", err=True)
        raise typer.Exit(code=2 if exc.usage_error else 1) from None
    for warning in result.warnings:
        typer.echo(f"warning: {warning}", err=True)
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    else:
        typer.echo(render(result, show_evidence=show_evidence))
