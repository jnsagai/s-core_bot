"""Typer app skeleton: global --config/--version, and common exit-code mapping.

Subcommands (`doctor`, `models`, `serve`) register themselves on `cli_app` in their own modules
and are imported here so the console script sees the full command set.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from score_docs_assistant import __version__
from score_docs_assistant.domain.errors import ConfigError, SnapshotError

# rich_markup_mode=None forces plain, undecorated Click-style help text everywhere, instead of
# Typer's default Rich-based rendering. Rich's own styling detection (the default when `rich` is
# transitively installed) force-enables ANSI codes when CI/GITHUB_ACTIONS env vars are set, even
# with no real TTY attached — which made `--help` output differ between a local run and GitHub
# Actions and broke a test asserting on plain help text (docs/ASSUMPTIONS.md A-011). Plain help
# also matches contracts/cli.md, which never specifies colored output.
cli_app = typer.Typer(add_completion=False, no_args_is_help=True, rich_markup_mode=None)


def handle_common_errors[F: Callable[..., Any]](func: F) -> F:
    """Maps `ConfigError` to exit 2, `SnapshotError` to exit 1 and `KeyboardInterrupt` to exit 130
    for every command."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ConfigError as exc:
            for path, reason in exc.errors:
                typer.echo(f"{path}: {reason}", err=True)
            raise typer.Exit(code=2) from None
        except SnapshotError as exc:
            typer.echo(f"{exc.code}: {exc.message}", err=True)
            raise typer.Exit(code=1) from None
        except KeyboardInterrupt:
            raise typer.Exit(code=130) from None

    return wrapper  # type: ignore[return-value]


@cli_app.callback()
def main_callback(
    ctx: typer.Context,
    config: Annotated[
        Path | None, typer.Option("--config", help="Path to a YAML config file.")
    ] = None,
    version: Annotated[
        bool, typer.Option("--version", help="Print the version and exit.", is_eager=True)
    ] = False,
) -> None:
    if version:
        typer.echo(f"score-assistant {__version__}")
        raise typer.Exit(code=0)
    ctx.obj = {"config_path": config}


def app() -> None:
    cli_app()


from score_docs_assistant.cli import bundle as _bundle  # noqa: E402,F401
from score_docs_assistant.cli import doctor as _doctor  # noqa: E402,F401
from score_docs_assistant.cli import index as _index  # noqa: E402,F401
from score_docs_assistant.cli import models as _models  # noqa: E402,F401
from score_docs_assistant.cli import serve as _serve  # noqa: E402,F401
from score_docs_assistant.cli import snapshots as _snapshots  # noqa: E402,F401
from score_docs_assistant.cli import sources as _sources  # noqa: E402,F401
