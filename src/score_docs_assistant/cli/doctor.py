"""`score-assistant doctor [--json]` (contracts/cli.md)."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from score_docs_assistant import __version__
from score_docs_assistant.cli.config_paths import profiles_path_for
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.cli.runtime_factory import build_runtime
from score_docs_assistant.config.loader import load_config
from score_docs_assistant.diagnostics.doctor import render_json, render_text, run_doctor
from score_docs_assistant.domain.errors import ConfigError, ProfileNotFound
from score_docs_assistant.models.profiles import get_profile, load_profiles
from score_docs_assistant.storage.corpus_probe import FileCorpusProbe


@cli_app.command("doctor")
@handle_common_errors
def doctor_command(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON instead of text.")
    ] = False,
) -> None:
    """Report local readiness: runtime, models, disk/memory, and corpus state."""
    config_path = (ctx.obj or {}).get("config_path")
    effective = load_config(config_path=config_path)
    config = effective.config

    profiles = load_profiles(profiles_path_for(effective.config_file or config_path))
    try:
        profile = get_profile(profiles, config.runtime.model_profile)
    except ProfileNotFound as exc:
        raise ConfigError(
            [("runtime.model_profile", f"unknown model profile: {exc.profile}")]
        ) from exc

    runtime = build_runtime(config)
    try:
        report = run_doctor(
            effective=effective,
            runtime=runtime,
            profile=profile,
            corpus_probe=FileCorpusProbe(config.data_dir),
            app_version=__version__,
        )
    finally:
        close = getattr(runtime, "close", None)
        if close is not None:
            close()

    if json_output:
        typer.echo(json.dumps(render_json(report, effective=effective)))
    else:
        typer.echo(render_text(report))
    raise typer.Exit(code=report.exit_code)
