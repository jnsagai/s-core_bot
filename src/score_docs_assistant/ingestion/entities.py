"""Need-entity construction shared by the RST and Markdown (MyST) parsers (FR-011, FR-018)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Literal

from score_docs_assistant.domain.ingestion import Entity, Severity
from score_docs_assistant.ingestion.links import parse_link_value

DiagFn = Callable[[str, Severity, str | None, int | None, str], None]


def build_entity(
    *,
    source_id: str,
    need_type: str,
    title: str,
    options: dict[str, str],
    link_options: set[str],
    document_key: str,
    path: str,
    line_start: int | None,
    line_end: int | None,
    id_counter: Counter[str],
    diag: DiagFn,
    origin: Literal["rst", "markdown"],
) -> Entity | None:
    """Return the entity, or None (with a diagnostic) when the need has no `:id:`. Keys are
    `<source_id>:<need_id>`; repeats within a source get `#n` in encounter order."""
    need_id = options.get("id", "").strip()
    if not need_id:
        diag("NEED_WITHOUT_ID", "warning", path, line_start, f"{need_type} without :id:")
        return None
    id_counter[need_id] += 1
    count = id_counter[need_id]
    key = f"{source_id}:{need_id}" + (f"#{count}" if count > 1 else "")
    if count > 1:
        diag(
            "DUPLICATE_ID_IN_SOURCE",
            "warning",
            path,
            line_start,
            f"need id {need_id!r} already defined in this source; kept as {key}",
        )
    links = [
        ref
        for name, value in options.items()
        if name in link_options
        for ref in parse_link_value(name, value)
    ]
    for ref in links:
        if ref.resolution == "malformed":
            diag(
                "MALFORMED_LINK",
                "warning",
                path,
                line_start,
                f"{ref.via} item {ref.raw!r} is not ID[qualifier]; kept raw",
            )
    return Entity(
        key=key,
        need_id=need_id,
        type=need_type,
        title=title,
        options=dict(options),
        links=links,
        source_id=source_id,
        document_key=document_key,
        path=path,
        line_start=line_start,
        line_end=line_end,
        origin=origin,
        revision_status="pinned",
    )
