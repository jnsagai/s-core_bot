"""`score-assistant search | lookup` (specs/004-hybrid-search/contracts/cli.md)."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Annotated, Any

import typer

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app, handle_common_errors
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


def _lines(start: int | None, end: int | None) -> str:
    if start is None:
        return ""
    return f":{start}" if end in (None, start) else f":{start}-{end}"


@cli_app.command("lookup")
@handle_common_errors
@handle_search_errors
def lookup_command(
    ctx: typer.Context,
    identifier: Annotated[str, typer.Argument(help="Requirement ID, or source_id:ID.")],
    snapshot: Annotated[
        str | None, typer.Option("--snapshot", help="Snapshot ID (default: active).")
    ] = None,
    source: Annotated[str | None, typer.Option("--source", help="Restrict to one source.")] = None,
    show_relationships: Annotated[
        bool, typer.Option("--relationships", help="Also list stored links.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Looks up a requirement ID exactly in one snapshot. Offline."""
    service = SearchService(config=_config(ctx), provider=None)
    response = service.lookup(identifier, snapshot_id=snapshot, source_id=source)
    relations = (
        [
            service.relationships(e.key, snapshot_id=response.snapshot_id, limit=200)
            for e in response.entities
        ]
        if show_relationships
        else []
    )
    if json_output:
        payload: dict[str, Any] = response.model_dump(mode="json")
        if show_relationships:
            payload["relationships"] = [r.model_dump(mode="json") for r in relations]
        import json

        typer.echo(json.dumps(payload, sort_keys=True))
        return
    typer.echo(f"snapshot {response.snapshot_id}")
    if response.status == "no_match":
        typer.echo(f'no exact match for "{response.query}"')
        return
    for index, entity in enumerate(response.entities):
        revision = (entity.revision or "-")[:12]
        typer.echo(
            f"[{entity.match}] {entity.key}  {entity.type}  {entity.title!r}  "
            f"status {entity.status or '-'}  {entity.source_id}@{revision} "
            f"({entity.revision_status})  {entity.path}{_lines(entity.line_start, entity.line_end)}"
        )
        if entity.excerpt:
            for line in entity.excerpt.splitlines()[:8]:
                typer.echo(f"    {line}")
        if show_relationships:
            rel = relations[index]
            typer.echo(f"  links: {rel.outgoing_total} outgoing, {rel.incoming_total} incoming")
            for item in rel.items:
                arrow = "->" if item.direction == "out" else "<-"
                other = item.target_id if item.direction == "out" else item.from_key
                typer.echo(f"    {arrow} {item.via}: {other} ({item.resolution})")


@cli_app.command("search")
@handle_common_errors
@handle_search_errors
def search_command(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Question or keywords.")],
    snapshot: Annotated[
        str | None, typer.Option("--snapshot", help="Snapshot ID (default: active).")
    ] = None,
    source: Annotated[
        list[str] | None, typer.Option("--source", help="Only this source (repeatable).")
    ] = None,
    kind: Annotated[
        list[str] | None,
        typer.Option(
            "--kind",
            help="Only this content kind (repeatable): prose, need, table, code, literal, diagram.",
        ),
    ] = None,
    limit: Annotated[
        int | None, typer.Option("--limit", help="Number of results (max 20).")
    ] = None,
    lexical: Annotated[
        bool, typer.Option("--lexical", help="Keyword and exact matching only.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Searches one snapshot offline; may use the local embedding runtime (no downloads, no
    generation)."""
    import json

    from pydantic import ValidationError

    from score_docs_assistant.domain.retrieval import SearchRequest

    config = _config(ctx)
    service = build_service(config, embeddings=not lexical)
    try:
        request = SearchRequest(
            query=query,
            snapshot_id=snapshot,
            limit=limit,
            sources=source or [],
            kinds=kind or [],  # type: ignore[arg-type]
        )
    except ValidationError as exc:
        raise SearchError("QUERY_INVALID", "; ".join(e["msg"] for e in exc.errors())) from None
    response = service.search(request, force_lexical=lexical)
    if json_output:
        typer.echo(json.dumps(response.model_dump(mode="json"), sort_keys=True))
        return
    if response.degraded is not None and response.degraded.reason != "lexical_requested":
        typer.echo(
            f"warning: semantic search unavailable ({response.degraded.reason}): "
            "keyword results only",
            err=True,
        )
        for hint in response.degraded.guidance:
            typer.echo(f"  guidance: {hint}", err=True)
    typer.echo(
        f"snapshot {response.snapshot_id}  mode {response.mode}  {len(response.results)} results"
    )
    if response.status == "no_results":
        typer.echo("no results")
    for result in response.results:
        section = " > ".join(result.heading_path)
        typer.echo(
            f"{result.rank:>2}. [{' '.join(result.matched_by)}] {result.source_id}  "
            f"{result.path}{_lines(result.line_start, result.line_end)}  ({result.kind})  {section}"
        )
        for line in result.excerpt.splitlines()[:4]:
            typer.echo(f"    {line[:160]}")
