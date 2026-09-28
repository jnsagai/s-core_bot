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


@index_app.command("validate")
@handle_common_errors
def validate_command(
    ctx: typer.Context,
    snapshot: Annotated[str, typer.Option("--snapshot", help="Snapshot ID to validate.")],
    json_output: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Validates a snapshot offline; may query the local runtime for model identity (never embeds).

    Exit 0 when no integrity check fails (semantic `disabled`/`unverified` are warnings), 1 on
    any integrity failure or an unknown snapshot.
    """
    from datetime import UTC, datetime

    from score_docs_assistant.domain.errors import SnapshotError
    from score_docs_assistant.storage.build import chunker_config
    from score_docs_assistant.storage.catalog import Catalog
    from score_docs_assistant.storage.manifest import dump_json
    from score_docs_assistant.storage.pins import Pin
    from score_docs_assistant.storage.validation import SnapshotValidator

    config = _config(ctx)
    catalog = Catalog.open(config.data_dir, create=False)
    if catalog is None:
        raise SnapshotError("SNAPSHOT_NOT_FOUND", "no catalog yet; run `index build` first")
    with catalog:
        row = catalog.get(snapshot)
    directory = config.data_dir / "snapshots" / snapshot
    if row is None or row.state in ("deleted", "building") or not directory.is_dir():
        state = "missing" if row is None else row.state
        raise SnapshotError("SNAPSHOT_NOT_FOUND", f"snapshot {snapshot} is {state}")
    try:
        runtime = runtime_factory.build_embedding_provider(config)
    except SnapshotError:
        runtime = None
    with Pin(config.data_dir, snapshot):
        report = SnapshotValidator(
            data_dir=config.data_dir,
            embedding_model=config.runtime.embedding_model,
            chunker_config=chunker_config(config),
            runtime=runtime,
        ).validate(directory, expected_manifest_sha256=row.manifest_sha256)
    reports = config.data_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (reports / f"validate-{snapshot}-{stamp}.json").write_bytes(dump_json(report))
    if json_output:
        typer.echo(report.model_dump_json())
    else:
        for check in report.integrity:
            if check.status == "fail":
                typer.echo(f"FAIL {check.id}: {check.detail}")
        verdict = "integrity ok" if report.integrity_ok else "integrity FAILED"
        typer.echo(f"{snapshot}: {verdict}")
        typer.echo(f"semantic: {report.semantic} ({report.semantic_detail})")
        for hint in report.guidance:
            typer.echo(f"  guidance: {hint}")
    raise typer.Exit(code=0 if report.integrity_ok else 1)
