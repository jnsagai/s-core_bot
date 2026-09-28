"""Shared helpers for the search, lookup, eval and ask commands.

Kept free of `cli.main` imports so any command module can be imported first.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import typer

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SearchError, SnapshotError
from score_docs_assistant.retrieval.service import SearchService


def _config(ctx: typer.Context) -> AppConfig:
    return load_config(config_path=(ctx.obj or {}).get("config_path")).config


def build_service(config: AppConfig, *, embeddings: bool = True) -> SearchService:
    provider = None
    if embeddings:
        try:
            provider = runtime_factory.build_embedding_provider(config)
        except SnapshotError:
            provider = None
    return SearchService(config=config, provider=provider)


def handle_search_errors[F: Callable[..., Any]](func: F) -> F:
    """SearchError → exit 2 for usage/validation problems, exit 1 otherwise."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except SearchError as exc:
            typer.echo(f"{exc.code}: {exc.message}", err=True)
            raise typer.Exit(code=2 if exc.usage_error else 1) from None

    return wrapper  # type: ignore[return-value]
