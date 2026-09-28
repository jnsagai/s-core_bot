"""`score-assistant sources validate|sync|inspect` (specs/002-source-ingestion/contracts/cli.md).

`--config` here is the *source registry*; the global `score-assistant --config` remains the app
configuration, which supplies `data_dir`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated

import httpx
import typer

from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.config.loader import load_config
from score_docs_assistant.ingestion.normalize import NormalizationService
from score_docs_assistant.ingestion.report import render_text, write_outputs, write_report
from score_docs_assistant.sources.git_client import GitClient
from score_docs_assistant.sources.lock import read_lock
from score_docs_assistant.sources.registry import load_registry
from score_docs_assistant.sources.sync import SyncService

sources_app = typer.Typer(add_completion=False, help="Manage approved documentation sources.")
cli_app.add_typer(sources_app, name="sources")

RegistryOption = Annotated[
    Path, typer.Option("--config", help="Source registry file (config/sources.yaml).")
]
DEFAULT_REGISTRY = Path("config/sources.yaml")


def build_http_client() -> httpx.Client | None:
    """Seam for tests; production lets `fetch_export` create a client with registry timeouts."""
    return None


def build_git_client(read_timeout_seconds: int) -> GitClient:
    """Seam for tests; production allows HTTPS only (research R5)."""
    return GitClient(low_speed_seconds=read_timeout_seconds)


def _data_dir(ctx: typer.Context) -> Path:
    effective = load_config(config_path=(ctx.obj or {}).get("config_path"))
    return effective.config.data_dir


@sources_app.command("validate")
@handle_common_errors
def validate_command(registry: RegistryOption = DEFAULT_REGISTRY) -> None:
    """Validate the source registry and its parser profiles. Offline."""
    loaded = load_registry(registry)
    typer.echo(f"{registry}: valid ({len(loaded.sources)} sources)")


@sources_app.command("sync")
@handle_common_errors
def sync_command(
    ctx: typer.Context,
    registry: RegistryOption = DEFAULT_REGISTRY,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    """Uses the network: resolves refs and downloads approved sources.

    Writes data/source-lock.json only if every required source succeeds; otherwise the previous
    lock and acquired files are left untouched.
    """
    loaded = load_registry(registry)
    service = SyncService(
        loaded,
        _data_dir(ctx),
        git=build_git_client(loaded.limits.read_timeout_seconds),
        http_client=build_http_client(),
        progress=lambda message: typer.echo(message, err=True),
    )
    outcome = service.run()
    if json_output:
        payload = {
            "lock_path": str(outcome.lock_path),
            "network_used": True,
            "sources": [
                {
                    "source_id": r.source_id,
                    "status": r.status,
                    "revision": r.revision,
                    "files": r.files,
                    "skipped": r.skipped,
                    "bytes": r.bytes,
                    "failure": r.failure,
                }
                for r in outcome.results
            ],
        }
        typer.echo(json.dumps(payload))
    elif outcome.exit_code == 0:
        typer.echo(f"Wrote {outcome.lock_path}")
    else:
        typer.echo("Sync failed; previous lock left unchanged.", err=True)
    raise typer.Exit(code=outcome.exit_code)


@sources_app.command("inspect")
@handle_common_errors
def inspect_command(
    ctx: typer.Context,
    lock: Annotated[Path, typer.Option("--lock", help="Source lock written by `sources sync`.")] = (
        Path("data/source-lock.json")
    ),
    profiles_dir: Annotated[
        Path, typer.Option("--profiles-dir", help="Directory of parser profiles.")
    ] = Path("config/parser-profiles"),
    json_output: Annotated[
        bool, typer.Option("--json", help="Print the full report as JSON.")
    ] = False,
    output: Annotated[
        Path | None, typer.Option("--output", help="Also write documents/entities as JSON Lines.")
    ] = None,
) -> None:
    """Normalize acquired sources offline and report coverage. Never uses the network."""
    lock_data = read_lock(lock)
    lock_sha = hashlib.sha256(lock.read_bytes()).hexdigest()
    data_dir = _data_dir(ctx)
    outcome = NormalizationService(lock_data, lock_sha, data_dir, profiles_dir).run()
    write_report(outcome.report, data_dir / "reports")
    if output is not None:
        write_outputs(outcome, output)
    if json_output:
        typer.echo(json.dumps(outcome.report.model_dump(mode="json"), sort_keys=True))
    else:
        typer.echo(render_text(outcome.report))
    raise typer.Exit(code=outcome.exit_code)
