"""`score-assistant index build|validate` (specs/003-snapshot-index/contracts/cli.md)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.storage.build import BuildService

index_app = typer.Typer(add_completion=False, help="Build and validate corpus snapshots.")
cli_app.add_typer(index_app, name="index")


def _config(ctx: typer.Context) -> AppConfig:
    return load_config(config_path=(ctx.obj or {}).get("config_path")).config


def _progress(message: str) -> None:
    typer.echo(message, err=True)


@index_app.command("build")
@handle_common_errors
def build_command(
    ctx: typer.Context,
    source_lock: Annotated[
        Path, typer.Option("--source-lock", help="Source lock written by `sources sync`.")
    ] = Path("data/source-lock.json"),
    profiles_dir: Annotated[
        Path, typer.Option("--profiles-dir", help="Directory of parser profiles.")
    ] = Path("config/parser-profiles"),
    lexical_only: Annotated[
        bool,
        typer.Option("--lexical-only", help="Build a keyword-only snapshot without embeddings."),
    ] = False,
    activate: Annotated[
        bool, typer.Option("--activate", help="Activate the snapshot after validation.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print a JSON result.")] = False,
) -> None:
    """Builds a snapshot offline; uses only the local embedding runtime (no downloads).

    The result is `validated` (integrity-checked, not an engineering approval) and is not
    served until activated.
    """
    config = _config(ctx)
    provider = None if lexical_only else runtime_factory.build_embedding_provider(config)
    after_publish = None
    if activate:
        from score_docs_assistant.storage.lifecycle import activate_under_lock

        def after_publish(catalog: Any, snapshot_id: str) -> list[str]:
            return activate_under_lock(
                config=config,
                catalog=catalog,
                snapshot_id=snapshot_id,
                runtime=provider,
                progress=_progress,
            )

    service = BuildService(
        config=config,
        profiles_dir=profiles_dir,
        provider=provider,
        lexical_only=lexical_only,
        progress=_progress,
    )
    result = service.run(source_lock, after_publish=after_publish)
    for warning in result.warnings:
        typer.echo(f"warning: {warning}", err=True)
    if json_output:
        payload = {
            "snapshot_id": result.snapshot_id,
            "state": result.state,
            "semantic": result.semantic,
            "counts": result.counts.model_dump(mode="json"),
            "embedded": {
                "reused": result.counts.embedded_reused,
                "new": result.counts.embedded_new,
            },
            "activated": result.activated,
            "duration_seconds": round(result.duration_seconds, 3),
            "network_used": "none" if lexical_only else "loopback-embedding-only",
        }
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        typer.echo(f"{result.snapshot_id}  {result.state}  semantic {result.semantic}")
    sys.stdout.flush()
