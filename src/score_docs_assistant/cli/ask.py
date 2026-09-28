"""`score-assistant ask` (specs/005-grounded-chat/contracts/cli.md)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

import typer

from score_docs_assistant.answers.service import AnswerService
from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.cli.search_support import _config, build_service, handle_search_errors
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.answers import AnswerEnvelope, ChatRequest
from score_docs_assistant.domain.errors import GenerationError


def build_answer_service(config: AppConfig) -> AnswerService:
    try:
        provider = runtime_factory.build_generation_provider(config)
    except GenerationError:
        provider = None
    return AnswerService(config=config, search=build_service(config), provider=provider)


def render(envelope: AnswerEnvelope, *, show_evidence: bool) -> str:
    model = (
        f"{envelope.model.name} ({envelope.model.digest[:12]})" if envelope.model else "not used"
    )
    lines = [f"snapshot {envelope.snapshot_id}  status {envelope.status}  model {model}"]
    for claim in envelope.claims:
        if claim.kind == "limitation":
            continue
        marker = "" if claim.kind == "documented" else f"({claim.kind}) "
        refs = " ".join(f"[{e}]" for e in claim.evidence_ids)
        lines.append(f"- {marker}{claim.text} {refs}".rstrip())
    if envelope.limitations:
        lines.append("limitations:")
        lines.extend(f"- {text}" for text in envelope.limitations)
    if envelope.citations:
        lines.append("citations:")
    for citation in envelope.citations:
        span = ""
        if citation.line_start is not None:
            span = f":{citation.line_start}-{citation.line_end}"
        lines.append(
            f"[{citation.evidence_id}] {citation.source_id}  {citation.path}{span}  "
            f"({citation.revision_status})"
        )
        if citation.immutable_url:
            lines.append(f"     {citation.immutable_url}")
        if show_evidence:
            lines.extend(f"     | {line}" for line in citation.excerpt.splitlines())
    return "\n".join(lines)


@cli_app.command("ask")
@handle_common_errors
@handle_search_errors
def ask_command(
    ctx: typer.Context,
    question: Annotated[str, typer.Argument(help="Your question.")],
    snapshot: Annotated[
        str | None, typer.Option("--snapshot", help="Snapshot ID (default: active).")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the answer envelope.")] = False,
    show_evidence: Annotated[
        bool, typer.Option("--show-evidence", help="Also print each cited excerpt.")
    ] = False,
) -> None:
    """Answers a question from one snapshot with the local model; cites stored evidence (no
    downloads)."""
    service = build_answer_service(_config(ctx))
    try:
        request = ChatRequest(question=question, snapshot_id=snapshot)
    except ValueError as exc:
        typer.echo(f"REQUEST_INVALID: {exc}", err=True)
        raise typer.Exit(code=2) from None
    try:
        envelope = asyncio.run(service.answer(request, request_id=uuid.uuid4().hex))
    except GenerationError as exc:
        typer.echo(f"{exc.code}: {exc.message}", err=True)
        raise typer.Exit(code=2 if exc.usage_error else 1) from None
    for warning in envelope.warnings:
        typer.echo(f"warning: {warning}", err=True)
    if json_output:
        typer.echo(json.dumps(envelope.model_dump(mode="json"), sort_keys=True))
    else:
        typer.echo(render(envelope, show_evidence=show_evidence))
