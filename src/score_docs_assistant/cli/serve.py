"""`score-assistant serve [--host H] [--port P]` (contracts/cli.md)."""

from __future__ import annotations

import json
import socket as socket_module
from typing import Annotated

import typer
import uvicorn

from score_docs_assistant import __version__
from score_docs_assistant.api.app import create_app
from score_docs_assistant.cli.config_paths import profiles_path_for
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.cli.runtime_factory import build_runtime
from score_docs_assistant.config.loader import load_config
from score_docs_assistant.domain.errors import ConfigError, ProfileNotFound
from score_docs_assistant.models.profiles import get_profile, load_profiles
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.storage.corpus_probe import FileCorpusProbe


def _check_port_available(host: str, port: int) -> None:
    family = socket_module.AF_INET6 if ":" in host else socket_module.AF_INET
    sock = socket_module.socket(family, socket_module.SOCK_STREAM)
    sock.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    finally:
        sock.close()


@cli_app.command("serve")
@handle_common_errors
def serve_command(
    ctx: typer.Context,
    host: Annotated[str | None, typer.Option("--host", help="Override server.host.")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Override server.port.")] = None,
) -> None:
    """Serve the loopback-only HTTP API: /health/live, /health/ready, /api/v1/capabilities."""
    config_path = (ctx.obj or {}).get("config_path")
    cli_overrides: dict[str, object] = {}
    if host is not None:
        cli_overrides["server.host"] = host
    if port is not None:
        cli_overrides["server.port"] = port

    try:
        effective = load_config(config_path=config_path, cli_overrides=cli_overrides)
    except ConfigError as exc:
        if any(path == "server.host" for path, _reason in exc.errors):
            typer.echo(
                "server.host: Remote exposure requires the public profile, which is not "
                "available in this release.",
                err=True,
            )
            raise typer.Exit(code=2) from None
        raise

    config = effective.config

    profiles = load_profiles(profiles_path_for(effective.config_file or config_path))
    try:
        profile = get_profile(profiles, config.runtime.model_profile)
    except ProfileNotFound as exc:
        raise ConfigError(
            [("runtime.model_profile", f"unknown model profile: {exc.profile}")]
        ) from exc

    try:
        _check_port_available(config.server.host, config.server.port)
    except OSError as exc:
        typer.echo(f"BIND_FAILED: {exc}", err=True)
        raise typer.Exit(code=1) from None

    runtime = build_runtime(config)
    readiness_service = ReadinessService(
        config=config,
        runtime=runtime,
        corpus_probe=FileCorpusProbe(config.data_dir),
        profile=profile,
    )
    app = create_app(config=config, readiness_service=readiness_service)

    typer.echo(
        json.dumps(
            {
                "event": "startup",
                "host": config.server.host,
                "port": config.server.port,
                "app_version": __version__,
                "profile": config.profile,
            }
        ),
        err=True,
    )

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        proxy_headers=False,
        server_header=False,
        forwarded_allow_ips=None,
        access_log=False,
        log_config=None,
    )
