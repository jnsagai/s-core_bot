"""`score-assistant bundle export|inspect|import` (specs/003-snapshot-index/contracts/cli.md).

All offline: bundle commands never open a network socket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.storage import bundles

bundle_app = typer.Typer(add_completion=False, help="Move snapshots as verified bundle files.")
cli_app.add_typer(bundle_app, name="bundle")


def _config(ctx: typer.Context) -> AppConfig:
    return load_config(config_path=(ctx.obj or {}).get("config_path")).config


@bundle_app.command("export")
@handle_common_errors
def export_command(
    ctx: typer.Context,
    snapshot: Annotated[str, typer.Option("--snapshot", help="Snapshot ID to export.")],
    output: Annotated[
        Path, typer.Option("--output", help="Bundle file to write (must not exist).")
    ],
    acknowledge: Annotated[
        str | None,
        typer.Option(
            "--acknowledge-license-review",
            help="Reason for redistributing documents that require license review.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Export a snapshot as one bundle file with per-file SHA-256. Offline."""
    result = bundles.export_bundle(
        config=_config(ctx), snapshot_id=snapshot, output=output, acknowledgement=acknowledge
    )
    if json_output:
        typer.echo(json.dumps({"path": str(result.path), "sha256": result.sha256}))
    else:
        typer.echo(f"wrote {result.path}")
        typer.echo(f"sha256 {result.sha256}")


@bundle_app.command("inspect")
@handle_common_errors
def inspect_command(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Bundle file.")],
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Show a bundle's identity, schema, counts, embedding and license notes. Writes nothing."""
    result = bundles.inspect_bundle(config=_config(ctx), path=path)
    manifest = result.manifest
    snap: dict[str, Any] = dict(result.snapshot_manifest)
    summary = {
        "snapshot_id": manifest.snapshot_id,
        "schema_version": manifest.schema_version,
        "corpus_schema_version": manifest.corpus_schema_version,
        "total_size": manifest.total_size,
        "entry_count": manifest.entry_count,
        "counts": snap.get("counts"),
        "semantic": snap.get("semantic"),
        "embedding": snap.get("embedding"),
        "source_revisions": snap.get("source_revisions"),
        "license_review": snap.get("license_review"),
        "license_acknowledgement": (
            manifest.license_acknowledgement.model_dump()
            if manifest.license_acknowledgement
            else None
        ),
    }
    if json_output:
        typer.echo(json.dumps(summary, sort_keys=True, default=str))
        return
    for key, value in summary.items():
        typer.echo(f"{key}: {json.dumps(value, default=str)}")


@bundle_app.command("import")
@handle_common_errors
def import_command(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Bundle file.")],
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Verify and register a bundle as a validated (never active) snapshot. Offline."""
    result = bundles.import_bundle(config=_config(ctx), path=path)
    if json_output:
        typer.echo(
            json.dumps(
                {"snapshot_id": result.snapshot_id, "already_present": result.already_present}
            )
        )
        return
    if result.already_present:
        typer.echo(f"{result.snapshot_id} already present (identical manifest); nothing to do")
    else:
        typer.echo(f"imported {result.snapshot_id} (validated, not active)")
    typer.echo(f"activate with: score-assistant snapshots activate {result.snapshot_id}")
