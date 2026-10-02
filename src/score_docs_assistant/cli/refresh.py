"""`score-assistant refresh` (specs/015-scheduled-refresh/contracts/cli.md).

Uses the network (allowlisted source hosts only). Exit codes: 0 up-to-date/activated, 1 failed,
2 configuration/usage, 3 held, 4 busy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli import sources as sources_cli
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.refresh.gate import PromotionGate
from score_docs_assistant.refresh.models import RefreshRun
from score_docs_assistant.refresh.service import RefreshService
from score_docs_assistant.refresh.state import state_path
from score_docs_assistant.sources.registry import load_registry


def build_gate(config: AppConfig) -> PromotionGate:
    from score_docs_assistant.retrieval.evaluation import exact_id_suite
    from score_docs_assistant.retrieval.service import SearchService

    search = SearchService(config=config, provider=None)
    return PromotionGate(config, exact_ids=lambda sid: exact_id_suite(search, snapshot_id=sid))


@cli_app.command("refresh")
@handle_common_errors
def refresh_command(
    ctx: typer.Context,
    sources: Annotated[
        Path, typer.Option("--sources", help="Source registry file.")
    ] = sources_cli.DEFAULT_REGISTRY,
    profiles_dir: Annotated[
        Path, typer.Option("--profiles-dir", help="Directory of parser profiles.")
    ] = Path("config/parser-profiles"),
    lexical_only: Annotated[
        bool, typer.Option("--lexical-only", help="Force a keyword-only build.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print a JSON result.")] = False,
) -> None:
    """Uses the network: brings the active snapshot up to date with upstream.

    Checks upstream cheaply, syncs and builds only when something changed, and activates the new
    snapshot only if it passes the promotion gate. Never run by `serve`.
    """
    config = load_config(config_path=(ctx.obj or {}).get("config_path")).config
    registry = load_registry(sources)
    service = RefreshService(
        config,
        registry,
        profiles_dir=profiles_dir,
        git=sources_cli.build_git_client(registry.limits.read_timeout_seconds),
        http_client=sources_cli.build_http_client(),
        provider_factory=lambda: runtime_factory.build_embedding_provider(config),
        gate_factory=build_gate,
        lexical_only=lexical_only,
        progress=lambda message: typer.echo(message, err=True),
    )
    run = service.run()
    if json_output:
        payload = json.loads(run.model_dump_json())
        payload["network_used"] = run.outcome != "busy"
        payload["state_path"] = str(state_path(config.data_dir))
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        typer.echo(render_text(run))
    raise typer.Exit(code=run.exit_code)


def render_text(run: RefreshRun) -> str:
    lines: list[str] = []
    for check in run.checks:
        change = ""
        if check.status == "changed" and check.upstream:
            change = f"{(check.locked or '-')[:7]} → {check.upstream[:7]}"
        lines.append(
            f"check  {check.source_id:<22} {check.status:<9}  {change or check.detail}".rstrip()
        )
    if run.synced:
        if run.lock_changed:
            lines.append(f"sync   lock updated ({len(run.revision_changes)} source(s) changed)")
        else:
            lines.append("sync   lock unchanged")
    if run.candidate:
        lines.append(f"build  {run.candidate}  ({run.timings.get('build', 0):.1f} s)")
    if run.gate:
        lines.append("gate   " + " | ".join(f"{g.id} {g.status} ({g.detail})" for g in run.gate))
    summary = f"{run.outcome}: {run.reason}"
    if run.outcome == "activated" and run.active_before:
        summary += f" (previous {run.active_before})"
    lines.append(summary)
    return "\n".join(lines)
