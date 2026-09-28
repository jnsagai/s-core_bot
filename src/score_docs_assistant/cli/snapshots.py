"""`score-assistant snapshots list|activate|rollback` (specs/003-snapshot-index/contracts/cli.md)."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.models.runtime import EmbeddingProvider
from score_docs_assistant.storage import lifecycle
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.pins import is_pinned

snapshots_app = typer.Typer(
    add_completion=False,
    help="List, activate and roll back corpus snapshots. "
    "'validated' means integrity-checked, not an engineering approval.",
)
cli_app.add_typer(snapshots_app, name="snapshots")


def _config(ctx: typer.Context) -> AppConfig:
    return load_config(config_path=(ctx.obj or {}).get("config_path")).config


def _runtime(config: AppConfig) -> EmbeddingProvider | None:
    try:
        return runtime_factory.build_embedding_provider(config)
    except SnapshotError:
        return None


def _progress(message: str) -> None:
    typer.echo(message, err=True)


@snapshots_app.command("list")
@handle_common_errors
def list_command(
    ctx: typer.Context,
    include_deleted: Annotated[
        bool, typer.Option("--all", help="Include deleted snapshots.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List snapshots, newest first. Offline."""
    config = _config(ctx)
    catalog = Catalog.open(config.data_dir, create=False)
    rows = []
    active = None
    if catalog is not None:
        with catalog:
            rows = catalog.snapshots(include_deleted=include_deleted)
            active = catalog.active_id()
    records: list[dict[str, Any]] = [
        {
            "snapshot_id": r.snapshot_id,
            "state": r.state,
            "semantic": r.semantic,
            "chunks": r.chunks,
            "created_at": r.created_at.isoformat(),
            "activated_at": r.activated_at.isoformat() if r.activated_at else None,
            "active": r.snapshot_id == active,
            "pinned": r.state != "deleted" and is_pinned(config.data_dir, r.snapshot_id),
        }
        for r in rows
    ]
    if json_output:
        typer.echo(json.dumps({"snapshots": records}, sort_keys=True))
        return
    if not records:
        typer.echo("No snapshots. Run `score-assistant index build`.")
        return
    typer.echo(f"  {'ID':<27} {'STATE':<9} {'SEMANTIC':<8} {'CHUNKS':>6}  CREATED  PINNED")
    for r in records:
        marker = "*" if r["active"] else " "
        typer.echo(
            f"{marker} {r['snapshot_id']:<27} {r['state']:<9} {r['semantic'] or '-':<8} "
            f"{r['chunks'] if r['chunks'] is not None else '-':>6}  {r['created_at'][:19]}  "
            f"{'yes' if r['pinned'] else 'no'}"
        )


@snapshots_app.command("activate")
@handle_common_errors
def activate_command(
    ctx: typer.Context,
    snapshot_id: Annotated[str, typer.Argument(help="Snapshot ID from `snapshots list`.")],
) -> None:
    """Activate a validated snapshot atomically after re-verifying its checksums.

    May query the local runtime for the embedding model identity; never downloads.
    """
    config = _config(ctx)
    warnings = lifecycle.activate(
        config=config, snapshot_id=snapshot_id, runtime=_runtime(config), progress=_progress
    )
    for warning in warnings:
        typer.echo(f"warning: {warning}", err=True)


@snapshots_app.command("rollback")
@handle_common_errors
def rollback_command(ctx: typer.Context) -> None:
    """Re-activate the snapshot that was active before the current one."""
    config = _config(ctx)
    warnings = lifecycle.rollback(config=config, runtime=_runtime(config), progress=_progress)
    for warning in warnings:
        typer.echo(f"warning: {warning}", err=True)
